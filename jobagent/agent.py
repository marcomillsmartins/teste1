"""Pré-filtro, ranqueamento (score) e preparação de candidaturas."""
from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path

import yaml

from . import llm
from .models import ApplicationPackage, Job, JobScore

log = logging.getLogger(__name__)


def load_yaml(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_cv(profile: dict) -> str:
    import os

    if os.environ.get("CV_MARKDOWN"):  # útil no GitHub Actions (segredo), sem commitar o CV
        return os.environ["CV_MARKDOWN"]
    path = Path(profile.get("cv_path", "cv/cv.md"))
    if not path.exists():
        raise SystemExit(
            f"CV não encontrado em {path}. Copie cv/cv.example.md para {path} e cole o seu CV."
        )
    return path.read_text(encoding="utf-8")


def prefilter(jobs: list[Job], cfg: dict) -> list[Job]:
    bad = [k.lower() for k in cfg.get("exclude_title_keywords", [])]
    max_age = cfg.get("max_age_days")
    cutoff = (date.today() - timedelta(days=max_age)).isoformat() if max_age else None
    today = date.today().isoformat()
    out = []
    for j in jobs:
        t = j.title.lower()
        if not j.title or any(k in t for k in bad):
            continue
        if cutoff and j.posted_date and j.posted_date < cutoff:
            continue
        if j.deadline and j.deadline < today:
            continue
        out.append(j)
    return out


def _profile_block(profile: dict, cv: str) -> str:
    p = {k: v for k, v in profile.items() if k not in ("cv_path", "cv_pdf_path")}
    return f"<perfil>\n{yaml.safe_dump(p, allow_unicode=True, sort_keys=False)}</perfil>\n\n<cv>\n{cv}\n</cv>"


SCORE_SYSTEM = """Você é um headhunter sênior especializado em clima, meio ambiente, políticas
públicas e advocacy no Brasil e na América Latina. Avalie com rigor e honestidade a aderência de
uma vaga ao candidato descrito no perfil e no CV. Considere área temática, senioridade, tipo de
empregador, localização/modalidade (São Paulo, Brasília, remoto, híbrido em SP, curta duração em
outros locais) e idiomas. Seja calibrado: 85+ só para vagas quase sob medida; abaixo de 50 se a
área ou senioridade não batem. Não penalize por requisitos "desejáveis"."""


def score_job(job: Job, profile: dict, cv: str) -> JobScore:
    return llm.structured_call(
        system=llm.cached_system(SCORE_SYSTEM, _profile_block(profile, cv)),
        user=f"Avalie esta vaga:\n\n{_job_block(job)}",
        output=JobScore,
        effort="medium",
        max_tokens=8000,
    )


WRITE_SYSTEM = """Você escreve candidaturas de alto nível para vagas em organizações
internacionais, fundações e ONGs. Regras inegociáveis:
- Use SOMENTE fatos presentes no CV e no perfil. Nunca invente cargos, números, datas, idiomas,
  diplomas ou conquistas. Se faltar algo que a vaga pede, não finja: destaque experiências próximas.
- Escreva no idioma da vaga (pt, en ou es).
- Carta de 250-400 palavras, concreta, conectando 2-3 conquistas do CV aos requisitos da vaga,
  mostrando conhecimento da organização apenas com base no texto da vaga. Tom profissional, sem clichês.
- Assine com o nome do perfil (se vazio, use "[Seu nome]").
- Em respostas de formulário sobre pretensão salarial ou dados pessoais desconhecidos, use
  marcadores como [PREENCHER] em vez de inventar."""


def prepare_application(job: Job, score: JobScore | None, profile: dict, cv: str) -> ApplicationPackage:
    extra = f"\n\nAnálise prévia de aderência:\n{score.model_dump_json(indent=2)}" if score else ""
    return llm.structured_call(
        system=llm.cached_system(WRITE_SYSTEM, _profile_block(profile, cv)),
        user=f"Prepare a candidatura para esta vaga:\n\n{_job_block(job)}{extra}",
        output=ApplicationPackage,
        effort="high",
        max_tokens=16000,
    )


def _job_block(job: Job) -> str:
    return (
        f"<vaga>\nTítulo: {job.title}\nOrganização: {job.organization}\nLocal: {job.location}\n"
        f"Fonte: {job.source}\nURL: {job.url}\nPublicada: {job.posted_date or '?'}\n"
        f"Prazo: {job.deadline or '?'}\nE-mail de candidatura: {job.apply_email or '-'}\n\n"
        f"{job.description[:8000]}\n</vaga>"
    )


def save_package(job_id: str, job: Job, pkg: ApplicationPackage, out_dir: str | Path = "output/applications") -> Path:
    d = Path(out_dir) / job_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "carta.md").write_text(pkg.cover_letter, encoding="utf-8")
    answers = "\n\n".join(f"**{a.question}**\n\n{a.answer}" for a in pkg.screening_answers)
    highlights = "\n".join(f"- {h}" for h in pkg.cv_highlights)
    (d / "candidatura.md").write_text(
        f"# {job.title} — {job.organization}\n\n"
        f"- Link: {job.url}\n- Local: {job.location}\n- Prazo: {job.deadline or '?'}\n"
        f"- Candidatura por e-mail: {job.apply_email or 'não (usar o link)'}\n\n"
        f"## Dicas antes de enviar\n\n{pkg.notes_for_candidate}\n\n"
        f"## E-mail\n\n**Assunto:** {pkg.email_subject}\n\n{pkg.email_body}\n\n"
        f"## Carta de apresentação\n\n{pkg.cover_letter}\n\n"
        f"## Destaques do CV para esta vaga\n\n{highlights}\n\n"
        f"## Respostas para formulário\n\n{answers}\n",
        encoding="utf-8",
    )
    return d
