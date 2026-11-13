"""Fontes de vagas. Cada fonte devolve uma lista de `Job`; falhas não derrubam a execução."""
from __future__ import annotations

import logging
from typing import Callable

from ..models import Job
from . import ats, gupy, reliefweb, web_search

log = logging.getLogger(__name__)


def collect(search_cfg: dict, profile: dict) -> list[Job]:
    runners: list[tuple[str, Callable[[], list[Job]]]] = []
    if search_cfg.get("gupy", {}).get("enabled"):
        runners.append(("gupy", lambda: gupy.fetch(search_cfg["gupy"])))
    if search_cfg.get("reliefweb", {}).get("enabled"):
        runners.append(("reliefweb", lambda: reliefweb.fetch(search_cfg["reliefweb"])))
    if search_cfg.get("greenhouse", {}).get("enabled"):
        runners.append(("greenhouse", lambda: ats.fetch_greenhouse(search_cfg["greenhouse"])))
    if search_cfg.get("lever", {}).get("enabled"):
        runners.append(("lever", lambda: ats.fetch_lever(search_cfg["lever"])))
    if search_cfg.get("web_search", {}).get("enabled"):
        runners.append(("web_search", lambda: web_search.fetch(search_cfg["web_search"], profile)))

    jobs: list[Job] = []
    for name, run in runners:
        try:
            found = run()
            log.info("%s: %d vagas", name, len(found))
            jobs += found
        except Exception as exc:  # uma fonte fora do ar não deve parar as outras
            log.warning("%s falhou: %s", name, exc)
    return jobs
