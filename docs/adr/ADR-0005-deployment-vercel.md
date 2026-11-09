# ADR-0005: Run everything on Vercel with serverless functions and external Postgres

## Status

Accepted

Amendment after verification against the current Vercel docs (FastAPI framework preset, `app.frontend()`, Fluid compute): the architecture below stands, but the implementation differs from what was originally written here. The backend does not need legacy `builds`/`routes` config or a WSGI wrapper. Vercel now detects FastAPI as a framework preset and runs the whole app, frontend included, as a single serverless function:

- Entrypoint: `app/main.py` exposing `app = FastAPI()`.
- The built frontend (`web/dist`) is served by `app.frontend("/", directory="web/dist", fallback="index.html")`. API routes take priority over frontend files. Static files are promoted to the CDN at build time. No CORS, one domain.
- `vercel.json`: `buildCommand` builds `web/`, `functions["app/main.py"].maxDuration = 60`.
- Dependencies: plain `requirements.txt` at the repo root.
- Bundle limit for FastAPI apps is 500 MB (not 250). Fluid compute is the default.

The "Vercel only, warts documented" decision is unchanged. The escape hatch is unchanged: the app is a standard FastAPI codebase and can move to a traditional host by changing the deploy config.

## Context

The project is developed and published through GitHub and Vercel, and the developer wants to keep that setup rather than run a separate backend host. Vercel is a frontend and serverless platform. It does not run a long-running FastAPI server process and hosts no database.

## Options considered

1. React on Vercel, FastAPI on a traditional host (Render, Fly, Railway) with managed Postgres.
2. Everything on Vercel: React frontend, FastAPI exposed as Vercel Python serverless functions, external managed Postgres on Neon.
3. A VPS with Docker Compose, both apps on one box.

## Decision

Option 2 for v1. The FastAPI app is structured from the start so it can run as Vercel serverless functions, with Postgres on Neon.

Reasons:

- One platform, one repo, deploy on push. Already the working setup.
- Free tier is sufficient for a single user and small audience.
- Neon over the alternatives because it is plain managed Postgres and nothing else. Supabase bundles auth, storage, and client libraries this project deliberately does not use in v1, so Supabase would be accepted complexity with no payoff.
- SQLite would be simpler but does not survive serverless filesystems, so external Postgres is required anyway.

## Constraints this forces

- PDF generation must be pure Python, drawing the document directly from resume data with fpdf2. WeasyPrint and headless browsers do not work in Vercel Python functions. fpdf2 over reportlab because it is the smaller dependency and enough for a single column ATS layout. This replaces the HTML-render approach in ADR-0004. ADR-0003's principle stands: generation happens from structured data, and DOCX via python-docx is unchanged (pure Python, works fine).
- Function timeout on the Hobby tier is 10 seconds by default, configurable to 60. The tailoring call sends a full resume plus a job description to an LLM and can take 15 to 40 seconds. The function must set maxDuration to 60 from the start, and the tailoring route needs a client timeout longer than the function timeout plus an honest error state.
- Function size limit 250 MB. Constraints on dependencies: keep the dependency list small and pure Python where possible.
- Cold starts on the free tier mean the first request after idle takes seconds. Acceptable for a personal tool.
- No background workers, no cron daemons, no long-lived processes on the free tier. Anything that needs those later is a reason to split the backend out to a traditional host.

## Consequences

- If tailoring calls ever exceed 60 seconds reliably, either upgrade the Vercel tier or move the FastAPI app to Render/Fly as-is. Because the app is already a standard FastAPI codebase, moving it later means changing the deploy config, not rewriting the app. This is the escape hatch.
- Being serverless means the PDF layout is code (fpdf2 positioning) rather than a shared HTML template. The visual double implementation noted in ADR-0004 remains, just in a different form: the React preview template versus the fpdf2 drawing code. One template on each side, kept deliberately simple, is still the v1 rule.
- Neon's free tier suspends databases after inactivity, so the first request after a break also pays a database wake-up. Acceptable for v1, noted so it is not mistaken for a bug.
