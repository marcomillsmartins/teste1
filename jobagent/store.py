"""Banco SQLite local: evita duplicatas e acompanha o status de cada vaga."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from .models import ApplicationPackage, Job, JobScore

STATUSES = ("new", "scored", "prepared", "approved", "applied", "skipped", "rejected", "interview")

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    score INTEGER,
    score_data TEXT,
    package TEXT,
    found_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    notes TEXT DEFAULT ''
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str | Path = "data/jobs.db"):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def add(self, jobs: Iterable[Job]) -> list[Job]:
        """Insere vagas novas; devolve só as que ainda não existiam."""
        new = []
        for job in jobs:
            cur = self.db.execute(
                "INSERT OR IGNORE INTO jobs (id, data, found_at, updated_at) VALUES (?,?,?,?)",
                (job.id, job.model_dump_json(), _now(), _now()),
            )
            if cur.rowcount:
                new.append(job)
        self.db.commit()
        return new

    def set_score(self, job_id: str, score: JobScore) -> None:
        self.db.execute(
            "UPDATE jobs SET score=?, score_data=?, status='scored', updated_at=? WHERE id=?",
            (score.fit_score, score.model_dump_json(), _now(), job_id),
        )
        self.db.commit()

    def set_package(self, job_id: str, pkg: ApplicationPackage) -> None:
        self.db.execute(
            "UPDATE jobs SET package=?, status='prepared', updated_at=? WHERE id=?",
            (pkg.model_dump_json(), _now(), job_id),
        )
        self.db.commit()

    def set_status(self, job_id: str, status: str, note: str = "") -> None:
        if status not in STATUSES:
            raise ValueError(f"status inválido: {status} (use {', '.join(STATUSES)})")
        self.db.execute(
            "UPDATE jobs SET status=?, updated_at=?, notes=COALESCE(notes,'') || ? WHERE id=?",
            (status, _now(), (f"\n[{_now()}] {note}" if note else ""), job_id),
        )
        self.db.commit()

    def get(self, job_id: str) -> Optional[dict]:
        row = self.db.execute("SELECT * FROM jobs WHERE id LIKE ?", (job_id + "%",)).fetchone()
        return self._row(row) if row else None

    def list(self, statuses: Optional[Iterable[str]] = None, min_score: int = 0) -> list[dict]:
        q = "SELECT * FROM jobs WHERE COALESCE(score, 0) >= ?"
        args: list = [min_score]
        if statuses:
            statuses = list(statuses)
            q += f" AND status IN ({','.join('?' * len(statuses))})"
            args += statuses
        q += " ORDER BY COALESCE(score, -1) DESC, found_at DESC"
        return [self._row(r) for r in self.db.execute(q, args)]

    @staticmethod
    def _row(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "job": Job.model_validate_json(row["data"]),
            "status": row["status"],
            "score": row["score"],
            "score_data": JobScore.model_validate_json(row["score_data"]) if row["score_data"] else None,
            "package": ApplicationPackage.model_validate_json(row["package"]) if row["package"] else None,
            "found_at": row["found_at"],
            "notes": row["notes"] or "",
        }


def export_json(store: Store) -> str:
    rows = store.list()
    return json.dumps(
        [
            {**r["job"].model_dump(), "id": r["id"], "status": r["status"], "score": r["score"]}
            for r in rows
        ],
        ensure_ascii=False,
        indent=2,
    )
