"""Relatório diário em Markdown com as vagas ranqueadas."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from .store import Store

LABEL = {"apply": "✅ candidatar", "maybe": "🤔 talvez", "skip": "⏭️ pular"}


def build(store: Store, min_score: int = 0, out_dir: str | Path = "output") -> Path:
    rows = [r for r in store.list(min_score=min_score) if r["status"] not in ("skipped", "rejected")]
    lines = [f"# Vagas — {date.today().isoformat()}", ""]
    if not rows:
        lines.append("Nenhuma vaga nova acima da nota mínima.")
    pending = [r for r in rows if r["status"] in ("scored", "prepared", "new")]
    done = [r for r in rows if r["status"] in ("approved", "applied", "interview")]
    for title, group in (("Para revisar", pending), ("Em andamento", done)):
        if not group:
            continue
        lines += [f"## {title} ({len(group)})", ""]
        for r in group:
            j, s = r["job"], r["score_data"]
            score = f"**{r['score']}**" if r["score"] is not None else "—"
            lines.append(f"### {score} · [{j.title}]({j.url}) — {j.organization}")
            lines.append(
                f"`{r['id']}` · {j.location or '?'} · {j.source} · prazo {j.deadline or '?'} · status: {r['status']}"
            )
            if s:
                lines.append(f"\n{LABEL[s.recommendation]} — {s.summary_pt}")
                if s.key_matches:
                    lines.append(f"- **Pontos fortes:** {'; '.join(s.key_matches[:4])}")
                if s.gaps:
                    lines.append(f"- **Lacunas:** {'; '.join(s.gaps[:3])}")
                if s.red_flags:
                    lines.append(f"- **Alertas:** {'; '.join(s.red_flags[:3])}")
            if r["package"]:
                lines.append(f"- 📝 Candidatura pronta em `output/applications/{r['id']}/candidatura.md`")
            lines.append("")
    path = Path(out_dir) / f"relatorio-{date.today().isoformat()}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
