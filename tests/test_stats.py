"""Statistics tests. The numbers drive charts and the CSV export, so the
definitions are asserted directly: a stage counts if it was ever reached,
and the response rate is measured against applications actually sent."""
import csv
import io

import pytest

from tests.conftest import signup


def _job(client, title, company="", source="", status=None):
    body = {"title": title, "company": company, "source": source}
    if status:
        body["status"] = status
    r = client.post("/api/jobs", json=body)
    assert r.status_code == 201
    return r.json()["id"]


def test_stats_require_auth(client):
    assert client.get("/api/stats").status_code == 401
    assert client.get("/api/stats/export.csv").status_code == 401


def test_empty_account_returns_zeroed_shape(client, new_email):
    signup(client, new_email)
    stats = client.get("/api/stats").json()
    assert stats["totals"]["jobs"] == 0
    assert stats["totals"]["response_rate"] == 0.0
    assert [row["stage"] for row in stats["funnel"]] == [
        "interested",
        "applied",
        "interview",
        "offer",
    ]
    assert len(stats["weekly"]) == 12
    assert len(stats["monthly_changes"]) == 6


def test_funnel_counts_stages_ever_reached(client, new_email):
    signup(client, new_email)
    a = _job(client, "A", "Acme", "LinkedIn")
    b = _job(client, "B", "Beta", "Indeed")
    c = _job(client, "C", "Gamma", "LinkedIn")
    # A: applied then rejected. B: applied then interview. C: never applied.
    client.patch(f"/api/jobs/{a}", json={"status": "applied"})
    client.patch(f"/api/jobs/{a}", json={"status": "rejected"})
    client.patch(f"/api/jobs/{b}", json={"status": "applied"})
    client.patch(f"/api/jobs/{b}", json={"status": "interview"})

    stats = client.get("/api/stats").json()
    funnel = {row["stage"]: row for row in stats["funnel"]}
    assert funnel["interested"]["count"] == 3
    assert funnel["applied"]["count"] == 2, "a rejected application still reached applied"
    assert funnel["interview"]["count"] == 1
    assert funnel["offer"]["count"] == 0

    # Percentages are relative to the top of the funnel, so the first stage
    # is 100% and never exceeds it.
    assert funnel["interested"]["pct_of_top"] == 100.0
    assert funnel["applied"]["pct_of_top"] == pytest.approx(66.7, abs=0.1)
    assert funnel["interview"]["pct_of_top"] == pytest.approx(33.3, abs=0.1)
    for row in stats["funnel"]:
        assert 0 <= row["pct_of_top"] <= 100, "a funnel stage cannot exceed its top"

    totals = stats["totals"]
    assert totals["applied"] == 2
    assert totals["responded"] == 1, "only B moved past applied"
    assert totals["response_rate"] == 50.0
    assert totals["active"] == 1, "B is still interview; A is rejected"


def test_by_status_and_sources(client, new_email):
    signup(client, new_email)
    _job(client, "A", "Acme", "LinkedIn")
    _job(client, "B", "Beta", "LinkedIn")
    _job(client, "C", "Gamma", "Indeed")
    stats = client.get("/api/stats").json()

    by_status = {row["status"]: row["count"] for row in stats["by_status"]}
    assert by_status["interested"] == 3
    assert [row["status"] for row in stats["by_status"]] == [
        "interested",
        "applied",
        "interview",
        "offer",
        "rejected",
        "closed",
    ]

    sources = {row["source"]: row["count"] for row in stats["sources"]}
    assert sources == {"LinkedIn": 2, "Indeed": 1}


def test_unspecified_source_is_grouped(client, new_email):
    signup(client, new_email)
    _job(client, "A")
    stats = client.get("/api/stats").json()
    assert stats["sources"][0]["source"] == "Unspecified"


def test_weekly_buckets_include_todays_jobs(client, new_email):
    signup(client, new_email)
    _job(client, "A")
    stats = client.get("/api/stats").json()
    assert sum(row["count"] for row in stats["weekly"]) == 1


def test_stats_are_isolated_per_user(client, new_email):
    other = f"other-{new_email}"
    signup(client, new_email)
    _job(client, "Mine", "Acme", "LinkedIn")

    client.cookies.clear()
    signup(client, other)
    stats = client.get("/api/stats").json()
    assert stats["totals"]["jobs"] == 0, "another account's jobs must not leak"


def test_csv_export_matches_the_numbers(client, new_email):
    signup(client, new_email)
    a = _job(client, "A", "Acme", "LinkedIn")
    client.patch(f"/api/jobs/{a}", json={"status": "applied"})

    r = client.get("/api/stats/export.csv")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "attachment" in r.headers["content-disposition"]
    assert "trackajob-statistics-" in r.headers["content-disposition"]

    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8"))))
    flat = {row[0]: row[1] for row in rows if len(row) >= 2}
    assert flat["Jobs"] == "1"
    assert flat["Applied"] == "1"
    assert flat["Response Rate"] == "0.0"
    # The section headings are present so a spreadsheet reads clearly.
    joined = "\n".join(",".join(row) for row in rows)
    for heading in ("Totals", "Current status", "Funnel", "Sources", "Companies"):
        assert heading in joined
