"""ReliefWeb: vagas de ONGs, ONU e cooperação internacional (https://apidoc.reliefweb.int)."""
from __future__ import annotations

import logging
import os

from ..models import Job
from .http import post_json, strip_html

log = logging.getLogger(__name__)
API = "https://api.reliefweb.int/v2/jobs"


def parse(item: dict) -> Job:
    f = item.get("fields", {})
    countries = ", ".join(c.get("name", "") for c in f.get("country", [])) or "Remoto/Não informado"
    org = ", ".join(s.get("name", "") for s in f.get("source", []))
    return Job(
        title=f.get("title", ""),
        organization=org,
        location=countries,
        url=f.get("url_alias") or f.get("url", ""),
        source="reliefweb",
        description=strip_html(f.get("body-html") or f.get("body", "")),
        posted_date=(f.get("date", {}).get("created") or "")[:10] or None,
        deadline=(f.get("date", {}).get("closing") or "")[:10] or None,
    )


def fetch(cfg: dict) -> list[Job]:
    appname = os.environ.get("RELIEFWEB_APPNAME")
    if not appname:
        log.info("reliefweb: defina RELIEFWEB_APPNAME para ativar esta fonte")
        return []
    jobs = []
    for q in cfg.get("queries", []):
        payload = {
            "query": {"value": q},
            "limit": 50,
            "sort": ["date.created:desc"],
            "fields": {"include": ["title", "url", "url_alias", "source.name", "country.name",
                                   "date.created", "date.closing", "body"]},
        }
        if cfg.get("countries"):
            payload["filter"] = {"field": "country.name", "value": cfg["countries"], "operator": "OR"}
        data = post_json(API, payload, params={"appname": appname})
        jobs += [parse(i) for i in data.get("data", [])]
    return jobs
