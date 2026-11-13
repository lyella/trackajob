"""Tests for the job tracker: creation, status workflow with history,
notes, per-user isolation, and the status filter."""
import json
import uuid

from sqlalchemy import text

from app.db import get_engine
from tests.conftest import signup


def _make_job(client, title="Backend Developer", company="Acme"):
    return client.post(
        "/api/jobs",
        json={
            "title": title,
            "company": company,
            "source": "pastetest",
            "url": "https://example.com/job",
            "description": "We are looking for a backend developer.",
        },
    )


def test_jobs_require_auth(client):
    assert client.get("/api/jobs").status_code == 401
    assert client.post("/api/jobs", json={"title": "x"}).status_code == 401


def test_create_list_and_invalid_status(client, new_email):
    signup(client, new_email)
    r = _make_job(client)
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "interested", "new jobs start interested"
    assert body["status_history"][0]["status"] == "interested"

    jobs = client.get("/api/jobs").json()
    assert [j["id"] for j in jobs] == [body["id"]]

    # A job saved after it was already applied to can open in that status;
    # the history still starts there rather than inventing an "interested".
    r = client.post("/api/jobs", json={"title": "Applied already", "status": "applied"})
    assert r.status_code == 201
    assert r.json()["status"] == "applied"
    assert [h["status"] for h in r.json()["status_history"]] == ["applied"]

    r = client.post("/api/jobs", json={"title": "Whatever", "statu": "applied"})
    assert r.status_code == 422, "unknown fields are still rejected"
    r = client.patch(f"/api/jobs/{body['id']}", json={"status": "dreamjob"})
    assert r.status_code == 422, "invalid statuses must never be stored"


def test_status_transitions_recorded_with_timestamps(client, new_email):
    signup(client, new_email)
    jid = _make_job(client).json()["id"]
    for status in ("applied", "interview", "rejected", "closed"):
        r = client.patch(f"/api/jobs/{jid}", json={"status": status})
        assert r.status_code == 200
        assert r.json()["status"] == status
    history = r.json()["status_history"]
    statuses = [h["status"] for h in history]
    assert statuses == ["interested", "applied", "interview", "rejected", "closed"]
    for entry in history:
        assert entry["at"], "every status change carries a timestamp"


def test_status_filter(client, new_email):
    signup(client, new_email)
    a = _make_job(client, title="A", company="Alpha").json()["id"]
    b = _make_job(client, title="B", company="Beta").json()["id"]
    client.patch(f"/api/jobs/{a}", json={"status": "applied"})
    listed = client.get("/api/jobs?status=applied").json()
    assert [j["id"] for j in listed] == [a]
    listed = client.get("/api/jobs?status=interested").json()
    assert [j["id"] for j in listed] == [b]


def test_notes_update(client, new_email):
    signup(client, new_email)
    jid = _make_job(client).json()["id"]
    r = client.patch(f"/api/jobs/{jid}", json={"notes": "Recruiter call on Friday"})
    assert r.status_code == 200
    assert r.json()["notes"] == "Recruiter call on Friday"


def test_get_single_job(client, new_email):
    signup(client, new_email)
    created = _make_job(client).json()
    r = client.get(f"/api/jobs/{created['id']}")
    assert r.status_code == 200, "fetching one saved job must not error"
    assert r.json()["title"] == created["title"]


def test_edits_advance_updated_at(client, new_email):
    signup(client, new_email)
    created = _make_job(client).json()
    r = client.patch(f"/api/jobs/{created['id']}", json={"notes": "edited"})
    assert r.status_code == 200
    assert r.json()["updated_at"] >= created["updated_at"]
    # The edit is timestamped in the history too, so the UI can show
    # "last touched" without guessing from a clock-skewed client.
    assert len(r.json()["status_history"]) >= 1


def test_users_cannot_see_or_touch_other_users_jobs(client, new_email):
    other = f"other-{uuid.uuid4().hex[:10]}@example.com"
    signup(client, new_email)
    jid = _make_job(client).json()["id"]

    client.cookies.clear()
    r = client.get("/api/jobs")
    assert r.status_code == 401

    signup(client, other)
    assert client.get("/api/jobs").json() == [], "other user sees an empty tracker"
    r = client.get(f"/api/jobs/{jid}")
    assert r.status_code == 404
    r = client.patch(f"/api/jobs/{jid}", json={"status": "applied"})
    assert r.status_code == 404, "must not mutate another user's job"
    r = client.delete(f"/api/jobs/{jid}")
    assert r.status_code == 404


def test_delete_job(client, new_email):
    signup(client, new_email)
    jid = _make_job(client).json()["id"]
    assert client.delete(f"/api/jobs/{jid}").status_code == 204
    assert client.get("/api/jobs").json() == []
    with get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT count(*) FROM jobs WHERE id = :i"), {"i": jid}
        ).scalar_one()
    assert row == 0, "deleted jobs are gone from storage, not hidden"
