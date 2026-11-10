"""M6 flow tests with a stubbed LLM boundary: tailoring appends a version,
guardrails strip unsupported bullets and warn, revert copies an old snapshot
forward, metering rows are written, and job linkage validates ownership."""
import json

import pytest

import app.tailoring
from tests.conftest import signup


BASE = {
    "name": "Stub User",
    "email": "s@example.com",
    "phone": "",
    "location": "",
    "links": [],
    "summary": "Backend developer with four years of experience.",
    "skills": ["Python", "PostgreSQL"],
    "experience": [
        {
            "company": "Acme",
            "role": "Backend Developer",
            "start": "2022-01",
            "end": None,
            "bullets": ["Built APIs serving thousands of daily requests"],
        }
    ],
    "education": [],
    "projects": [],
}


def _stub_llm(monkeypatch, tailored: dict, usage: dict | None = None):
    def fake(resume, job_text, prompt):
        return tailored, usage or {"prompt_tokens": 100, "completion_tokens": 50}

    monkeypatch.setattr(app.tailoring, "call_chat_completion", fake)


def _setup(client, new_email):
    signup(client, new_email)
    r = client.post("/api/resumes", json={"name": "master", "content": BASE})
    assert r.status_code == 201
    rid = r.json()["id"]
    r = client.post(
        "/api/jobs",
        json={
            "title": "Payments Backend",
            "company": "PayCo",
            "description": "We need someone for payment processing and reconciliation.",
        },
    )
    assert r.status_code == 201
    jid = r.json()["id"]
    return rid, jid


def test_tailor_appends_version_and_meters(monkeypatch, client, new_email):
    tailored = dict(BASE)
    tailored["summary"] = "Payments-focused backend developer."
    _stub_llm(monkeypatch, tailored)

    rid, jid = _setup(client, new_email)
    r = client.post(f"/api/resumes/{rid}/tailor", json={"job_id": jid, "prompt": "emphasize payments"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["version"] == 2 and body["base_version"] == 1
    assert body["content"]["summary"] == "Payments-focused backend developer."
    assert body["tokens_in"] == 100 and body["tokens_out"] == 50
    assert body["cost_usd"] > 0

    versions = client.get(f"/api/resumes/{rid}/versions").json()
    assert [v["version"] for v in versions] == [1, 2]

    usage = client.get("/api/tailor/usage").json()
    assert usage["calls"] == 1
    assert usage["tokens_in"] == 100

    latest = client.get(f"/api/resumes/{rid}").json()
    assert latest["version"] == 2


def test_tailor_strips_unsupported_bullets_and_warns(monkeypatch, client, new_email):
    tailored = dict(BASE)
    tailored["experience"] = [
        {
            "company": "Acme",
            "role": "Backend Developer",
            "start": "2022-01",
            "end": None,
            "bullets": [
                "Built APIs serving thousands of daily requests",
                "Led a migration to Google Cloud infrastructure",
            ],
        }
    ]
    _stub_llm(monkeypatch, tailored)

    rid, jid = _setup(client, new_email)
    r = client.post(f"/api/resumes/{rid}/tailor", json={"job_id": jid, "prompt": ""})
    assert r.status_code == 200
    content = r.json()["content"]
    bullets = content["experience"][0]["bullets"]
    assert bullets == ["Built APIs serving thousands of daily requests"], "fabricated bullet stripped"
    assert any("fabricated" in w.lower() for w in r.json()["warnings"]), "warning must be surfaced"


def test_tailor_requires_auth_and_ownership(client, new_email):
    rid, jid = _setup(client, new_email)
    client.cookies.clear()
    assert client.post(f"/api/resumes/{rid}/tailor", json={"job_id": jid}).status_code == 401


def test_revert_copies_old_snapshot_forward(monkeypatch, client, new_email):
    tailored = dict(BASE)
    tailored["summary"] = "Changed summary."
    _stub_llm(monkeypatch, tailored)
    rid, jid = _setup(client, new_email)
    client.post(f"/api/resumes/{rid}/tailor", json={"job_id": jid, "prompt": ""})

    r = client.post(f"/api/resumes/{rid}/revert", json={"version": 1})
    assert r.status_code == 200
    assert r.json() == {"version": 3, "reverted_from": 1}
    latest = client.get(f"/api/resumes/{rid}").json()
    assert json.loads(latest["content"])["summary"] == BASE["summary"], "revert restored v1 content"
    # history is append-only: all versions still present
    versions = client.get(f"/api/resumes/{rid}/versions").json()
    assert [v["version"] for v in versions] == [1, 2, 3]
    # reverting the latest version is a conflict
    assert client.post(f"/api/resumes/{rid}/revert", json={"version": 3}).status_code == 409


def test_job_linkage_records_resume_version(monkeypatch, client, new_email):
    tailored = dict(BASE)
    tailored["summary"] = "Tailored summary."
    _stub_llm(monkeypatch, tailored)
    rid, jid = _setup(client, new_email)
    r = client.post(f"/api/resumes/{rid}/tailor", json={"job_id": jid, "prompt": ""})
    version_id = r.json()["version_id"]

    r = client.patch(
        f"/api/jobs/{jid}", json={"status": "applied", "resume_version_id": version_id}
    )
    assert r.status_code == 200
    assert r.json()["resume_version_id"] == version_id
    assert r.json()["sent_resume"] == "master v2", "job shows which version was sent"

    # a version from another user's resume must not link
    other = "intruder@example.com"
    r = client.patch(f"/api/jobs/{jid}", json={"resume_version_id": 999999})
    assert r.status_code == 422
    assert other is not None
    # and clearing the linkage works
    r = client.patch(f"/api/jobs/{jid}", json={"resume_version_id": None})
    assert r.json()["resume_version_id"] is None
