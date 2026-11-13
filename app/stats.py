"""Application statistics.

Everything is computed from the job rows the user already has, so there is
no second source of truth. The shape is fixed and small: the frontend draws
it, and the CSV export writes the same numbers, so a chart and a spreadsheet
can never disagree.

Definitions, stated once so the UI and the export agree:

- funnel: how many applications ever reached a given stage, taken from the
  status history (not just the current status). An application that is now
  "rejected" still counts as having reached "applied".
- pct_of_top: a stage's share of everything tracked, so the first stage is
  100% and later stages read as retention.
- pct_of_applied: a stage's share of applications actually sent.
- response rate: of the applications that were actually sent (history
  contains "applied"), the share that moved past "applied".
- active: current status in applied/interview/offer.
"""

from __future__ import annotations

import csv
import io
import json
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import JobPost, User

STATUS_ORDER = ["interested", "applied", "interview", "offer", "rejected", "closed"]
# Progression order for the funnel. Rejected and closed are outcomes, not
# stages, so they are reported separately.
FUNNEL_ORDER = ["interested", "applied", "interview", "offer"]
ACTIVE_STATUSES = {"applied", "interview", "offer"}
POSITIVE = {"interview", "offer"}


def _parse(iso: str) -> datetime | None:
    if not iso:
        return None
    try:
        value = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _history(job: JobPost) -> list[dict]:
    try:
        data = json.loads(job.status_history or "[]")
    except json.JSONDecodeError:
        return []
    return [e for e in data if isinstance(e, dict) and e.get("status")]


def compute_stats(db: Session, user: User) -> dict:
    jobs = list(db.execute(select(JobPost).where(JobPost.user_id == user.id)).scalars())
    total = len(jobs)

    by_status = Counter(job.status for job in jobs)
    sources = Counter((job.source or "Unspecified").strip() or "Unspecified" for job in jobs)
    companies = Counter((job.company or "").strip() for job in jobs if (job.company or "").strip())

    # Funnel: a stage counts if it appears anywhere in the history.
    reached: Counter[str] = Counter()
    applied_jobs = 0
    responded = 0
    offers = 0
    for job in jobs:
        stages = {entry.get("status") for entry in _history(job)}
        stages.add(job.status)
        for stage in FUNNEL_ORDER:
            if stage in stages:
                reached[stage] += 1
        if "applied" in stages:
            applied_jobs += 1
            if stages & POSITIVE:
                responded += 1
        if "offer" in stages:
            offers += 1

    # Percentages are relative to the top of the funnel (everything that was
    # tracked), so the first stage is always 100% and later stages read as
    # retention. Dividing by "applied" made the first stage exceed 100%.
    funnel_top = reached["interested"] or total or 1
    funnel = [
        {
            "stage": stage,
            "count": reached[stage],
            "pct_of_top": round(reached[stage] / funnel_top * 100, 1),
            "pct_of_applied": round(reached[stage] / applied_jobs * 100, 1)
            if applied_jobs
            else 0.0,
        }
        for stage in FUNNEL_ORDER
    ]

    # Weekly activity over the last 12 weeks, by the date a job was saved.
    today = datetime.now(timezone.utc).replace(tzinfo=None).date()
    weeks: list[dict] = []
    for offset in range(11, -1, -1):
        start = today - timedelta(days=today.weekday() + 7 * offset)
        end = start + timedelta(days=7)
        count = sum(1 for job in jobs if job.created_at and start <= job.created_at.date() < end)
        weeks.append({"week_start": start.isoformat(), "count": count})

    # Status changes over time, by month, for a trend line.
    changes: Counter[str] = Counter()
    for job in jobs:
        for entry in _history(job):
            when = _parse(str(entry.get("at") or ""))
            if when:
                changes[when.strftime("%Y-%m")] += 1
    months: list[dict] = []
    cursor = today.replace(day=1)
    for _ in range(6):
        key = cursor.strftime("%Y-%m")
        months.append({"month": key, "count": changes.get(key, 0)})
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    months.reverse()

    active = sum(by_status[s] for s in ACTIVE_STATUSES)

    return {
        "totals": {
            "jobs": total,
            "active": active,
            "applied": applied_jobs,
            "responded": responded,
            "offers": offers,
            "rejected": by_status.get("rejected", 0),
            "response_rate": round(responded / applied_jobs * 100, 1) if applied_jobs else 0.0,
            "offer_rate": round(offers / applied_jobs * 100, 1) if applied_jobs else 0.0,
            "with_resume": sum(1 for job in jobs if job.resume_version_id),
        },
        "by_status": [
            {"status": status, "count": by_status.get(status, 0)} for status in STATUS_ORDER
        ],
        "funnel": funnel,
        "sources": [
            {"source": name, "count": count}
            for name, count in sorted(sources.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        "companies": [
            {"company": name, "count": count}
            for name, count in sorted(companies.items(), key=lambda kv: (-kv[1], kv[0]))[:8]
        ],
        "weekly": weeks,
        "monthly_changes": months,
    }


def stats_to_csv(stats: dict) -> str:
    """Flat, spreadsheet-friendly export of the same numbers the charts show."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")

    writer.writerow(["TrackAJob statistics export"])
    writer.writerow(["Generated", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")])
    writer.writerow([])

    writer.writerow(["Totals"])
    writer.writerow(["Metric", "Value"])
    for key, value in stats["totals"].items():
        writer.writerow([key.replace("_", " ").title(), value])
    writer.writerow([])

    writer.writerow(["Current status"])
    writer.writerow(["Status", "Count"])
    for row in stats["by_status"]:
        writer.writerow([row["status"].title(), row["count"]])
    writer.writerow([])

    writer.writerow(["Funnel (reached stage at any point)"])
    writer.writerow(["Stage", "Count", "Percent of tracked", "Percent of applied"])
    for row in stats["funnel"]:
        writer.writerow(
            [row["stage"].title(), row["count"], row["pct_of_top"], row["pct_of_applied"]]
        )
    writer.writerow([])

    writer.writerow(["Sources"])
    writer.writerow(["Source", "Count"])
    for row in stats["sources"]:
        writer.writerow([row["source"], row["count"]])
    writer.writerow([])

    writer.writerow(["Companies"])
    writer.writerow(["Company", "Count"])
    for row in stats["companies"]:
        writer.writerow([row["company"], row["count"]])
    writer.writerow([])

    writer.writerow(["Applications saved per week"])
    writer.writerow(["Week starting", "Count"])
    for row in stats["weekly"]:
        writer.writerow([row["week_start"], row["count"]])
    writer.writerow([])

    writer.writerow(["Status changes per month"])
    writer.writerow(["Month", "Count"])
    for row in stats["monthly_changes"]:
        writer.writerow([row["month"], row["count"]])

    return buf.getvalue()
