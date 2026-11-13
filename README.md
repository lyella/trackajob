# TrackAJob

Track your job applications and tailor your resume to each job post.

Status: pre-release. See PRD.md for the full vision, PLAN.md for the current
milestone plan, and docs/adr/ for decision records.

## Layout

- `app/` FastAPI backend (single Vercel Function; also serves the frontend)
- `web/` React + TypeScript frontend, built with Vite
- `cli/` tailoring spike used on real applications until the in-app flow lands
- `docs/` PRD, plan, ADRs

## Local development

Backend (Python 3.12+):

    python -m venv .venv
    .venv/Scripts/activate    # Windows
    pip install -r requirements.txt
    uvicorn app.main:app --reload

The API now runs at http://localhost:8000. GET /api/health is the sanity check.
Without setup it uses a local SQLite file; copy `.env.example` to `.env` and
set `DATABASE_URL` to point it at Postgres or Neon.

Frontend (Node 20+), in a second terminal:

    cd web
    npm install
    npm run dev

Runs at http://localhost:5173 with /api proxied to the backend.

## Frontend structure

- `web/src/App.tsx` app shell: header, nav, auth gate, bookmarklet handoff.
- `web/src/router.ts` hash router. Every screen is a real URL
  (`#/resumes`, `#/resumes/3`, `#/applications?status=applied&q=stripe`), so
  refresh, Back/Forward, and shared links all work.
- `web/src/ui.tsx` design primitives: buttons, fields with accessible
  labels, toasts, confirm dialogs, empty states, status pills.
- `web/src/styles.css` design tokens. Light and dark themes are one token
  swap driven by `prefers-color-scheme`; motion is disabled under
  `prefers-reduced-motion`.
- `web/src/format.ts` all date and number formatting goes through `Intl`.

## API surface the UI relies on

| Method | Path | Purpose |
| --- | --- | --- |
| `PATCH` | `/api/resumes/{id}` | Rename a resume (metadata only, no new version) |
| `DELETE` | `/api/resumes/{id}` | Delete a resume and its versions, unlinking applications |
| `GET` | `/api/resumes/{id}/export/{pdf,docx}?version=N` | Export the latest or a specific version |
| `POST` | `/api/jobs` | Create a job, optionally with an opening `status` |
| `GET` | `/api/jobs/{id}` | Fetch one saved job |

## Tailoring spike (cli/)

Requires an OpenAI-compatible API key. Copy `.env.example` to `.env`, then:

    python cli/tailor.py cli/sample/resume.json cli/sample/job.txt --out tailored

Writes `tailored.json` and a rough `tailored.pdf`, prints a change summary,
call duration, token usage, and estimated cost.

## Deployment

One Vercel project, one domain, no CORS:

- `vercel.json` builds `web/` and registers FastAPI at `app/main.py` with a 60
  second max duration.
- `app.main` mounts the built frontend via `app.frontend()`; API routes under
  `/api/` take priority.
- Set `DATABASE_URL` (Neon) as an environment variable in the Vercel project.

When you push to main, Vercel deploys. Deployment details: docs/adr/ADR-0005.
