"""Quadros de vagas Greenhouse e Lever de organizações específicas (APIs públicas)."""
from __future__ import annotations

from datetime import datetime, timezone

from ..models import Job
from .http import get_json, strip_html


def parse_greenhouse(item: dict, board: str) -> Job:
    return Job(
        title=item.get("title", ""),
        organization=board,
        location=(item.get("location") or {}).get("name", ""),
        url=item.get("absolute_url", ""),
        source="greenhouse",
        description=strip_html(item.get("content", "")),
        posted_date=(item.get("updated_at") or "")[:10] or None,
    )


def fetch_greenhouse(cfg: dict) -> list[Job]:
    jobs = []
    for board in cfg.get("boards", []):
        data = get_json(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs", params={"content": "true"})
        jobs += [parse_greenhouse(i, board) for i in data.get("jobs", [])]
    return jobs


def parse_lever(item: dict, company: str) -> Job:
    created = item.get("createdAt")
    posted = datetime.fromtimestamp(created / 1000, timezone.utc).date().isoformat() if created else None
    cats = item.get("categories") or {}
    return Job(
        title=item.get("text", ""),
        organization=company,
        location=cats.get("location", "") + (f" ({item['workplaceType']})" if item.get("workplaceType") else ""),
        url=item.get("hostedUrl", ""),
        source="lever",
        description=(item.get("descriptionPlain") or strip_html(item.get("description", "")))[:6000],
        posted_date=posted,
    )


def fetch_lever(cfg: dict) -> list[Job]:
    jobs = []
    for company in cfg.get("companies", []):
        data = get_json(f"https://api.lever.co/v0/postings/{company}", params={"mode": "json"})
        jobs += [parse_lever(i, company) for i in data]
    return jobs
