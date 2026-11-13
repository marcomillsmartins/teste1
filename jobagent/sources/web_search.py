"""Busca na web com o Claude (ferramenta web_search do servidor).

Cobre Google/LinkedIn/Indeed/Devex/Impactpool/UNjobs/sites de fundações etc. sem
raspagem direta: o Claude busca, abre as páginas e devolve uma lista estruturada.
"""
from __future__ import annotations

from datetime import date

from .. import llm
from ..models import FoundJobs, Job

SYSTEM = """Você é um pesquisador de vagas de emprego. Use a busca na web para encontrar
vagas ABERTAS e REAIS que se encaixem no perfil abaixo. Regras:
- Inclua apenas vagas que você viu nos resultados ou páginas abertas, com URL específica da vaga
  (não a página inicial de carreiras). Nunca invente vagas, URLs, datas ou e-mails.
- Descarte vagas claramente encerradas, de estágio/júnior, ou fora da área.
- Prefira vagas publicadas nos últimos 30 dias.
- Se a mesma vaga aparecer em vários sites, liste uma vez (prefira o site da organização).
- Campos desconhecidos ficam como string vazia."""


def fetch(cfg: dict, profile: dict) -> list[Job]:
    tool = {"type": "web_search_20260209", "name": "web_search", "max_uses": int(cfg.get("max_searches", 15))}
    if cfg.get("allowed_domains"):
        tool["allowed_domains"] = cfg["allowed_domains"]

    queries = "\n".join(f"- {q}" for q in cfg.get("queries", []))
    user = f"""Hoje é {date.today().isoformat()}.

Perfil do candidato (resumo):
{llm.dumps({k: profile.get(k) for k in ("areas", "target_roles", "target_employers", "locations", "seniority", "dealbreakers")})}

Faça buscas inspiradas nestas consultas (adapte e combine como achar melhor):
{queries}

Devolva até 40 vagas relevantes."""

    result = llm.structured_call(
        system=SYSTEM, user=user, output=FoundJobs, effort="medium", tools=[tool], max_tokens=32000
    )
    return [
        Job(
            title=j.title,
            organization=j.organization,
            location=j.location,
            url=j.url,
            source=f"web:{j.source_site}",
            description=j.summary,
            posted_date=j.posted_date or None,
            deadline=j.deadline or None,
            apply_email=j.apply_email or None,
        )
        for j in result.jobs
        if j.url.startswith("http")
    ]
