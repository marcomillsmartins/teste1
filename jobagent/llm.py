"""Chamadas ao Claude com saída estruturada (JSON validado por Pydantic)."""
from __future__ import annotations

import copy
import json
import logging
import os
from typing import Optional, Type, TypeVar

import anthropic
from pydantic import BaseModel

log = logging.getLogger(__name__)

MODEL = os.environ.get("JOBAGENT_MODEL", "claude-opus-5-5")
# Em caso de recusa pelos classificadores de segurança, a API refaz o pedido
# num modelo alternativo escolhido automaticamente (raro neste caso de uso).
FALLBACK_BETA = "server-side-fallback-2026-07-01"

T = TypeVar("T", bound=BaseModel)

_client: Optional[anthropic.Anthropic] = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(max_retries=4)
    return _client


class LLMError(RuntimeError):
    pass


def json_schema_for(model: Type[BaseModel]) -> dict:
    """Schema JSON do Pydantic, com $defs embutidos e additionalProperties=false."""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def resolve(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return resolve(copy.deepcopy(defs[node["$ref"].split("/")[-1]]))
            node = {k: resolve(v) for k, v in node.items() if k not in ("title", "default")}
            if node.get("type") == "object":
                node["additionalProperties"] = False
                node["required"] = list(node.get("properties", {}).keys())
            return node
        if isinstance(node, list):
            return [resolve(x) for x in node]
        return node

    return resolve(schema)


def structured_call(
    *,
    system: list[dict] | str,
    user: str,
    output: Type[T],
    effort: str = "medium",
    tools: Optional[list[dict]] = None,
    max_tokens: int = 16000,
    max_continuations: int = 8,
) -> T:
    """Envia um pedido e devolve a resposta já validada como `output`.

    Lida com `pause_turn` (busca na web longa) e com recusas.
    """
    messages: list[dict] = [{"role": "user", "content": user}]
    kwargs = dict(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        betas=[FALLBACK_BETA],
        fallbacks="default",
        output_config={
            "effort": effort,
            "format": {"type": "json_schema", "schema": json_schema_for(output)},
        },
    )
    if tools:
        kwargs["tools"] = tools

    for _ in range(max_continuations):
        resp = client().beta.messages.create(messages=messages, **kwargs)
        usage = resp.usage
        log.debug(
            "uso: in=%s out=%s cache_read=%s",
            usage.input_tokens, usage.output_tokens, getattr(usage, "cache_read_input_tokens", 0),
        )
        if resp.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": resp.content})
            continue
        if resp.stop_reason == "refusal":
            raise LLMError(f"Pedido recusado pelo modelo: {resp.stop_details}")
        if resp.stop_reason == "max_tokens":
            raise LLMError("Resposta cortada por max_tokens; aumente o limite.")
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        try:
            return output.model_validate_json(text)
        except Exception as exc:  # JSON inválido não deveria ocorrer com output_config.format
            raise LLMError(f"Resposta não pôde ser validada: {exc}\n{text[:500]}") from exc
    raise LLMError("Muitas continuações (pause_turn) seguidas.")


def cached_system(*blocks: str) -> list[dict]:
    """Bloco de sistema com cache: perfil + CV se repetem em todas as chamadas."""
    out = [{"type": "text", "text": b} for b in blocks if b]
    if out:
        out[-1]["cache_control"] = {"type": "ephemeral"}
    return out


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)
