from __future__ import annotations

import html
import re

import requests

UA = "Mozilla/5.0 (compatible; personal-job-agent/1.0)"
session = requests.Session()
session.headers["User-Agent"] = UA


def get_json(url: str, **kw):
    r = session.get(url, timeout=30, **kw)
    r.raise_for_status()
    return r.json()


def post_json(url: str, payload: dict, **kw):
    r = session.post(url, json=payload, timeout=30, **kw)
    r.raise_for_status()
    return r.json()


def strip_html(text: str, limit: int = 6000) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text or "", flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>|</p>|</li>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return text[:limit]
