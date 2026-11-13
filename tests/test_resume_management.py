"""Tests for resume management the UI depends on: renaming, deleting (with
its effect on application records), and exporting a specific version rather
than only the latest."""
import uuid
from io import BytesIO

from docx import Document
from sqlalchemy import text

from app.db import get_engine
from tests.conftest import signup

CONTENT = {
    "name": "Ada Lovelace",
    "email": "ada@example.com",
    "links": [],
    "skills": ["Analytical engines"],
    "experience": [],
    "education": [],
    "projects": [],
}


def _make_resume(client, name="Ada base"):
    r = client.post("/api/resumes", json={"name": name, "content": CONTENT})
    assert r.status_code == 201
    return r.json()["id"]


def test_rename_resume_does_not_create_a_version(client, new_email):
    signup(client, new_email)
    rid = _make_resume(client)
    r = client.patch(f"/api/resumes/{rid}", json={"name": "Ada — Stripe"})
    assert r.status_code == 200
    assert r.json()["name"] == "Ada — Stripe"
    assert r.json()["latest_version"] == 1, "renaming is metadata, not content"


def test_rename_rejects_empty_name(client, new_email):
    signup(client, new_email)
    rid = _make_resume(client)
    assert client.patch(f"/api/resumes/{rid}", json={"name": ""}).status_code == 422


def test_delete_resume_removes_versions_and_unlinks_jobs(client, new_email):
    signup(client, new_email)
    rid = _make_resume(client)
    job = client.post("/api/jobs", json={"title": "Engineer"}).json()
    with get_engine().begin() as conn:
        vid = conn.execute(
            text("SELECT id FROM resume_versions WHERE resume_id = :r"), {"r": rid}
        ).scalar_one()
    r = client.patch(f"/api/jobs/{job['id']}", json={"resume_version_id": vid})
    assert r.status_code == 200
    assert r.json()["sent_resume"] == "Ada base v1"

    assert client.delete(f"/api/resumes/{rid}").status_code == 204
    assert client.get("/api/resumes").json() == []
    assert client.get(f"/api/resumes/{rid}").status_code == 404

    kept = client.get(f"/api/jobs/{job['id']}").json()
    assert kept["resume_version_id"] is None, "the record survives, the dead link does not"
    assert kept["sent_resume"] is None


def test_export_a_specific_version(client, new_email):
    signup(client, new_email)
    rid = _make_resume(client)
    edited = dict(CONTENT, summary="SECONDVERSION marker text")
    r = client.post(f"/api/resumes/{rid}/versions", json=edited)
    assert r.status_code == 201
    assert r.json()["version"] == 2

    latest = client.get(f"/api/resumes/{rid}/export/pdf")
    assert latest.status_code == 200, "latest version still exports as before"

    docx_latest = client.get(f"/api/resumes/{rid}/export/docx")
    assert docx_latest.status_code == 200

    v1 = client.get(f"/api/resumes/{rid}/export/docx?version=1")
    assert v1.status_code == 200
    v1_text = "\n".join(p.text for p in Document(BytesIO(v1.content)).paragraphs)
    v2_text = "\n".join(p.text for p in Document(BytesIO(docx_latest.content)).paragraphs)
    assert "SECONDVERSION" not in v1_text
    assert "SECONDVERSION" in v2_text

    assert client.get(f"/api/resumes/{rid}/export/docx?version=99").status_code == 404


def test_resume_management_is_scoped_to_the_owner(client, new_email):
    other = f"other-{uuid.uuid4().hex[:10]}@example.com"
    signup(client, new_email)
    rid = _make_resume(client)

    client.cookies.clear()
    signup(client, other)
    assert client.patch(f"/api/resumes/{rid}", json={"name": "hijack"}).status_code == 404
    assert client.delete(f"/api/resumes/{rid}").status_code == 404
    assert client.get(f"/api/resumes/{rid}/export/docx?version=1").status_code == 404
