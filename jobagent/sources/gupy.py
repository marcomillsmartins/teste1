"""Gupy: API pública usada pelo portal https://portal.gupy.io."""
from __future__ import annotations

from ..models import Job
from .http import get_json, strip_html

API = "https://portal.api.gupy.io/api/job"


def parse(item: dict) -> Job:
    city, state = item.get("city") or "", item.get("state") or ""
    workplace = item.get("workplaceType") or ("remote" if item.get("isRemoteWork") else "")
    location = ", ".join(x for x in (city, state) if x)
    if workplace:
        location = f"{location} ({workplace})" if location else workplace
    return Job(
        title=item.get("name", ""),
        organization=item.get("careerPageName", ""),
        location=location,
        url=item.get("jobUrl", ""),
        source="gupy",
        description=strip_html(item.get("description", "")),
        posted_date=(item.get("publishedDate") or "")[:10] or None,
        deadline=(item.get("applicationDeadline") or "")[:10] or None,
    )


def fetch(cfg: dict) -> list[Job]:
    jobs = []
    for term in cfg.get("terms", []):
        data = get_json(API, params={"name": term, "offset": 0, "limit": 50})
        jobs += [parse(i) for i in data.get("data", [])]
    return jobs
