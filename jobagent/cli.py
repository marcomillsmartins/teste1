"""Linha de comando: python -m jobagent <comando>"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import webbrowser
from pathlib import Path

from . import agent, mailer, report, sources
from .store import STATUSES, Store

log = logging.getLogger("jobagent")


def load_dotenv(path: str = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            if v.strip():
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def confirm(question: str) -> bool:
    return input(f"{question} [s/N] ").strip().lower() in ("s", "sim", "y", "yes")


class App:
    def __init__(self, args):
        self.args = args
        self.profile = agent.load_yaml(args.profile)
        self.cfg = agent.load_yaml(args.search)
        self.store = Store(args.db)
        self._cv = None

    @property
    def cv(self) -> str:
        if self._cv is None:
            self._cv = agent.load_cv(self.profile)
        return self._cv

    # ---- etapas ----
    def search(self) -> int:
        jobs = agent.prefilter(sources.collect(self.cfg, self.profile), self.cfg)
        new = self.store.add(jobs)
        print(f"🔎 {len(jobs)} vagas após o pré-filtro; {len(new)} novas.")
        return len(new)

    def score(self) -> None:
        pending = self.store.list(statuses=["new"])[: int(self.cfg.get("max_jobs_to_score", 60))]
        _ = self.cv  # falha cedo se o CV não existir
        for i, r in enumerate(pending, 1):
            try:
                s = agent.score_job(r["job"], self.profile, self.cv)
            except Exception as exc:
                log.warning("falha ao ranquear %s: %s", r["id"], exc)
                continue
            self.store.set_score(r["id"], s)
            print(f"[{i}/{len(pending)}] {s.fit_score:3d} {s.recommendation:5s} {r['job'].title} — {r['job'].organization}")

    def prepare(self, ids: list[str] | None = None) -> None:
        if ids:
            rows = [self.store.get(i) for i in ids]
            rows = [r for r in rows if r]
        else:
            threshold = int(self.cfg.get("min_score_to_prepare", 70))
            rows = [r for r in self.store.list(statuses=["scored"], min_score=threshold)
                    if r["score_data"] and r["score_data"].recommendation != "skip"]
        for r in rows:
            try:
                pkg = agent.prepare_application(r["job"], r["score_data"], self.profile, self.cv)
            except Exception as exc:
                log.warning("falha ao preparar %s: %s", r["id"], exc)
                continue
            self.store.set_package(r["id"], pkg)
            path = agent.save_package(r["id"], r["job"], pkg)
            print(f"📝 {r['job'].title} — {r['job'].organization}: {path}/candidatura.md")

    def report(self) -> None:
        path = report.build(self.store, min_score=self.args.min_score)
        print(f"📄 Relatório: {path}")

    # ---- comandos ----
    def cmd_run(self):
        self.search()
        self.score()
        self.prepare()
        self.report()

    def cmd_search(self):
        self.search()

    def cmd_score(self):
        self.score()

    def cmd_prepare(self):
        self.prepare(self.args.ids or None)

    def cmd_report(self):
        self.report()

    def cmd_list(self):
        statuses = self.args.status.split(",") if self.args.status else None
        for r in self.store.list(statuses=statuses, min_score=self.args.min_score):
            j = r["job"]
            sc = f"{r['score']:3d}" if r["score"] is not None else "  -"
            print(f"{r['id']}  {sc}  {r['status']:9s} {j.title[:60]} — {j.organization[:30]} ({j.location[:25]})")

    def cmd_show(self):
        r = self._get(self.args.id)
        j, s = r["job"], r["score_data"]
        print(f"{j.title} — {j.organization}\n{j.location} · {j.url}\nstatus: {r['status']}\n")
        if s:
            print(f"Nota {s.fit_score} ({s.recommendation}): {s.summary_pt}")
            print("Pontos fortes:", "; ".join(s.key_matches))
            print("Lacunas:", "; ".join(s.gaps))
        if r["package"]:
            print(f"\nCandidatura: output/applications/{r['id']}/candidatura.md")

    def cmd_apply(self):
        """Semi-automático: você revisa, confirma, e só então o agente envia/abre."""
        r = self._get(self.args.id)
        if not r["package"]:
            print("Preparando candidatura primeiro...")
            self.prepare([r["id"]])
            r = self._get(r["id"])
        job, pkg = r["job"], r["package"]
        folder = agent.save_package(r["id"], job, pkg)
        print(f"\n===== {job.title} — {job.organization} =====")
        print(f"Revise antes de enviar: {folder}/candidatura.md\n")
        print(f"Dicas: {pkg.notes_for_candidate}\n")

        if job.apply_email:
            print(f"Para: {job.apply_email}\nAssunto: {pkg.email_subject}\n\n{pkg.email_body}\n\n{pkg.cover_letter}\n")
            if not confirm(f"Enviar este e-mail para {job.apply_email} agora?"):
                print("Nada enviado. Edite os arquivos e rode novamente quando quiser.")
                return
            body = f"{pkg.email_body}\n\n{pkg.cover_letter}"
            cv_pdf = Path(self.profile.get("cv_pdf_path") or "cv/cv.pdf")
            mailer.send(job.apply_email, pkg.email_subject, body, attachments=[cv_pdf])
            self.store.set_status(r["id"], "applied", f"e-mail enviado para {job.apply_email}")
            print("✅ Enviado e marcado como 'applied'.")
        else:
            print(f"Esta vaga é por formulário/site: {job.url}")
            if not self.args.no_browser:
                webbrowser.open(job.url)
            print("Use a carta e as respostas do arquivo acima para preencher o formulário.")
            if confirm("Você concluiu a candidatura? Marcar como 'applied'?"):
                self.store.set_status(r["id"], "applied", "candidatura via site")
                print("✅ Marcado como 'applied'.")

    def cmd_status(self):
        r = self._get(self.args.id)
        self.store.set_status(r["id"], self.args.status, self.args.note or "")
        print(f"{r['id']} -> {self.args.status}")

    def _get(self, job_id: str) -> dict:
        r = self.store.get(job_id)
        if not r:
            sys.exit(f"Vaga {job_id} não encontrada (use `list`).")
        return r


def main(argv=None):
    load_dotenv()
    p = argparse.ArgumentParser(prog="jobagent", description="Agente de busca e candidatura a vagas")
    p.add_argument("--profile", default="config/profile.yaml")
    p.add_argument("--search", default="config/search.yaml")
    p.add_argument("--db", default="data/jobs.db")
    p.add_argument("--min-score", type=int, default=0)
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run", help="buscar + ranquear + preparar + relatório (rotina diária)")
    sub.add_parser("search", help="só buscar vagas novas")
    sub.add_parser("score", help="ranquear vagas novas com o Claude")
    sp = sub.add_parser("prepare", help="gerar carta/e-mail/respostas")
    sp.add_argument("ids", nargs="*", help="ids das vagas (vazio = todas acima da nota mínima)")
    sub.add_parser("report", help="gerar relatório Markdown")
    sl = sub.add_parser("list", help="listar vagas")
    sl.add_argument("--status", help=f"filtrar: {','.join(STATUSES)}")
    ss = sub.add_parser("show", help="detalhes de uma vaga")
    ss.add_argument("id")
    sa = sub.add_parser("apply", help="revisar e enviar uma candidatura (pede confirmação)")
    sa.add_argument("id")
    sa.add_argument("--no-browser", action="store_true")
    st = sub.add_parser("status", help="mudar status (ex.: interview, rejected, skipped)")
    st.add_argument("id")
    st.add_argument("status", choices=STATUSES)
    st.add_argument("--note")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    getattr(App(args), f"cmd_{args.cmd}")()


if __name__ == "__main__":
    main()
