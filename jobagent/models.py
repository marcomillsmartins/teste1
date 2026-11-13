"""Modelos de dados (Pydantic) usados no banco e nas saídas estruturadas do Claude."""
from __future__ import annotations

import hashlib
import re
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class Job(BaseModel):
    """Uma vaga encontrada em qualquer fonte."""

    title: str
    organization: str = ""
    location: str = ""
    url: str = ""
    source: str = ""
    description: str = ""
    posted_date: Optional[str] = None  # ISO (AAAA-MM-DD) quando conhecido
    deadline: Optional[str] = None
    apply_email: Optional[str] = None

    @property
    def id(self) -> str:
        key = _norm_url(self.url) or f"{self.organization}|{self.title}".lower()
        return hashlib.sha1(key.encode()).hexdigest()[:12]


def _norm_url(url: str) -> str:
    url = (url or "").strip().lower()
    url = re.sub(r"[?#].*$", "", url)
    return url.rstrip("/")


# ---------- Saídas estruturadas do Claude (todos os campos obrigatórios) ----------


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FoundJob(_Strict):
    title: str
    organization: str
    location: str = Field(description="Cidade/país ou 'Remoto'/'Híbrido'")
    url: str = Field(description="Link direto para a vaga, exatamente como visto na busca")
    source_site: str
    summary: str = Field(description="2-4 frases com o que a vaga pede")
    posted_date: str = Field(description="AAAA-MM-DD ou '' se desconhecido")
    deadline: str = Field(description="AAAA-MM-DD ou '' se desconhecido")
    apply_email: str = Field(description="E-mail para candidatura, ou '' se não houver")


class FoundJobs(_Strict):
    jobs: list[FoundJob]


class JobScore(_Strict):
    fit_score: int = Field(description="0-100: aderência da vaga ao perfil e CV")
    recommendation: Literal["apply", "maybe", "skip"]
    location_ok: bool
    seniority_ok: bool
    posting_language: Literal["pt", "en", "es", "other"]
    key_matches: list[str]
    gaps: list[str]
    red_flags: list[str]
    summary_pt: str = Field(description="Resumo em português, 2-3 frases, do porquê da nota")


class ScreeningAnswer(_Strict):
    question: str
    answer: str


class ApplicationPackage(_Strict):
    language: Literal["pt", "en", "es"]
    cover_letter: str
    email_subject: str
    email_body: str = Field(description="Corpo curto do e-mail de candidatura (carta vai anexa/abaixo)")
    cv_highlights: list[str] = Field(description="5-8 bullets do CV para destacar nesta vaga")
    screening_answers: list[ScreeningAnswer] = Field(
        description="Respostas a perguntas típicas de formulário (motivação, pretensão, disponibilidade...)"
    )
    notes_for_candidate: str = Field(description="Dicas em português antes de enviar (o que revisar/ajustar)")
