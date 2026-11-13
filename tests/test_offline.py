"""Testes sem rede: simulam a API do Claude e as fontes. Rode: python -m pytest -q"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from jobagent import agent, llm, report
from jobagent.models import ApplicationPackage, FoundJobs, Job, JobScore
from jobagent.sources import ats, gupy, reliefweb
from jobagent.store import Store


def test_schema_is_strict_and_inlined():
    s = llm.json_schema_for(FoundJobs)
    assert "$defs" not in json.dumps(s)
    item = s["properties"]["jobs"]["items"]
    assert item["additionalProperties"] is False
    assert set(item["required"]) == set(item["properties"])
    pkg = llm.json_schema_for(ApplicationPackage)
    assert pkg["properties"]["screening_answers"]["items"]["additionalProperties"] is False


def test_parsers():
    g = gupy.parse({"name": "Coord. de Advocacy", "careerPageName": "ONG X", "city": "São Paulo",
                    "state": "SP", "workplaceType": "hybrid", "jobUrl": "https://x.gupy.io/jobs/1",
                    "publishedDate": "2026-11-01T10:00:00Z"})
    assert g.location == "São Paulo, SP (hybrid)" and g.posted_date == "2026-11-01"
    r = reliefweb.parse({"fields": {"title": "Climate Officer", "source": [{"name": "UNDP"}],
                                    "country": [{"name": "Brazil"}], "url": "https://rw/1",
                                    "date": {"closing": "2026-12-01T00:00:00+00:00"}}})
    assert r.organization == "UNDP" and r.deadline == "2026-12-01"
    lv = ats.parse_lever({"text": "Policy Lead", "hostedUrl": "https://jobs.lever.co/a/1",
                          "categories": {"location": "Remote"}, "createdAt": 1762000000000}, "a")
    assert lv.title == "Policy Lead" and lv.posted_date


def test_prefilter_and_dedupe(tmp_path):
    jobs = [
        Job(title="Advocacy Manager", url="https://a.org/job/1?utm=x"),
        Job(title="Advocacy Manager", url="https://a.org/job/1/"),  # duplicata
        Job(title="Estágio em Sustentabilidade", url="https://b.org/2"),
        Job(title="Old job", url="https://c.org/3", deadline="2000-01-01"),
    ]
    kept = agent.prefilter(jobs, {"exclude_title_keywords": ["estágio"], "max_age_days": 30})
    assert len(kept) == 2
    store = Store(tmp_path / "db.sqlite")
    assert len(store.add(kept)) == 1
    assert len(store.add(kept)) == 0


class FakeMessages:
    def __init__(self, payloads):
        self.payloads, self.calls = list(payloads), []

    def create(self, **kw):
        self.calls.append(kw)
        p = self.payloads.pop(0)
        if p == "PAUSE":
            return SimpleNamespace(stop_reason="pause_turn", content=[SimpleNamespace(type="server_tool_use")],
                                   usage=SimpleNamespace(input_tokens=1, output_tokens=1))
        return SimpleNamespace(stop_reason="end_turn", stop_details=None,
                               content=[SimpleNamespace(type="text", text=json.dumps(p))],
                               usage=SimpleNamespace(input_tokens=1, output_tokens=1, cache_read_input_tokens=0))


@pytest.fixture
def fake_llm(monkeypatch):
    def install(payloads):
        fm = FakeMessages(payloads)
        monkeypatch.setattr(llm, "_client", SimpleNamespace(beta=SimpleNamespace(messages=fm)))
        return fm
    return install


SCORE = {"fit_score": 88, "recommendation": "apply", "location_ok": True, "seniority_ok": True,
         "posting_language": "en", "key_matches": ["NbS"], "gaps": [], "red_flags": [],
         "summary_pt": "Muito aderente."}
PKG = {"language": "en", "cover_letter": "Dear team...", "email_subject": "Application",
       "email_body": "Please find...", "cv_highlights": ["x"],
       "screening_answers": [{"question": "Why?", "answer": "Because."}], "notes_for_candidate": "Revise."}


def test_end_to_end_with_fake_claude(fake_llm, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fm = fake_llm(["PAUSE", {"jobs": [{"title": "Climate Policy Lead", "organization": "Fund",
                                        "location": "Remote", "url": "https://fund.org/jobs/9",
                                        "source_site": "devex", "summary": "Lead policy.",
                                        "posted_date": "", "deadline": "", "apply_email": "jobs@fund.org"}]},
                   SCORE, PKG])
    from jobagent.sources import web_search

    found = web_search.fetch({"queries": ["q"], "max_searches": 3}, {"areas": ["clima"]})
    assert found[0].apply_email == "jobs@fund.org" and found[0].posted_date is None
    first = fm.calls[0]
    assert first["model"] == "claude-opus-5-5" and first["fallbacks"] == "default"
    assert first["tools"][0]["type"] == "web_search_20260209"
    assert len(fm.calls[1]["messages"]) == 2  # pause_turn foi reenviado

    store = Store("data/jobs.db")
    store.add(found)
    jid = found[0].id
    s = agent.score_job(found[0], {"name": "Teste"}, "CV")
    assert fm.calls[2]["system"][-1]["cache_control"] == {"type": "ephemeral"}
    store.set_score(jid, s)
    pkg = agent.prepare_application(found[0], s, {}, "CV")
    store.set_package(jid, pkg)
    folder = agent.save_package(jid, found[0], pkg)
    assert "Dear team" in (folder / "candidatura.md").read_text()
    md = report.build(store).read_text()
    assert "Climate Policy Lead" in md and "88" in md


def test_refusal_raises(fake_llm, monkeypatch):
    fm = fake_llm([])
    fm.create = lambda **kw: SimpleNamespace(stop_reason="refusal", stop_details="x", content=[],
                                             usage=SimpleNamespace(input_tokens=0, output_tokens=0))
    with pytest.raises(llm.LLMError):
        llm.structured_call(system="s", user="u", output=JobScore)


def test_mail_build(tmp_path):
    from jobagent import mailer
    pdf = tmp_path / "cv.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    m = mailer.build_message("a@b.org", "Assunto", "Corpo", "me@x.com", [pdf])
    assert m["To"] == "a@b.org" and any(p.get_filename() == "cv.pdf" for p in m.iter_attachments())
