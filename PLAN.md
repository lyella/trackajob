# PLAN.md: TrackAJob

Working plan for the first release described in PRD.md. This revision reflects two changes from the previous plan: development is AI-assisted end to end, and hosting is GitHub plus Vercel.

## Assumptions

- One developer, part time, roughly 10 hours a week, working with an AI coding agent throughout.
- Comfortable on one side of the stack (Python or React), learning the other by review rather than from scratch.
- AI assistance roughly halves the coding time versus the previous 24 week plan. The remaining bottleneck is judgment and review: evaluating tailoring output against real job posts, testing exports in Word and Google Docs, and making product decisions. Those do not speed up, and they cap the project at the developer's available hours.
- Publishing through GitHub and Vercel, as ADR-0005 records. FastAPI runs as Vercel serverless functions, Postgres is external on Neon.
- Personal tool first, portfolio project second. PRD.md remains the full vision. Cuts are tracked under Deferred.

## Approach

The tailor is the product. The riskiest parts, an LLM call that rewrites resume content against a job description, and the Vercel serverless constraints, are both proven in week 2 as a command line tool. That tool is not a throwaway. It stays installed and gets used on real applications from week 2 until the full flow replaces it in M6. If the tailoring output disappoints, or the LLM call cannot fit a serverless function, the plan changes before months have gone into it.

After the spike: minimal login, resume builder with one template, PDF and DOCX export, tracker as a plain list, then the full tailoring flow with diff and revert.

## Using it before it is finished

The point of TrackAJob is helping the developer get a job, and the developer is job hunting now. Two rules follow:

- From week 2, every real application gets tailored through the CLI spike, crude as it is. If the CLI output is not good enough to send, fixing the prompt and model is the top priority, ahead of any milestone.

- The job search is never paused for the build. The job search never waits on v1. Any week where the build and the applications conflict, the applications win; milestones stretch, and that is fine.

## Tech stack summary

- Frontend: React with TypeScript, built with Vite, deployed to Vercel. Plain CSS to start.
- Backend: Python, FastAPI, running as Vercel serverless functions per ADR-0005.
- Database: SQLite locally, Turso (libSQL, free tier) in production, accessed through SQLAlchemy. Postgres on Neon stays provisioned as the documented fallback, see ADR-0006. Neon's bundled services were removed to keep the stack strictly free (ADR-0005 amendment).
- AI: a hosted LLM through an API, provider picked during the spike based on output quality and cost per call.
- Export: PDF drawn with fpdf2 directly from resume data (pure Python, small dependency, serverless safe, enough for a single column ATS layout). DOCX written with python-docx. No headless browsers, no WeasyPrint, see ADR-0005.

## v1 scope cuts

- Job board imports (LinkedIn, Indeed, JobStreet, MCP connectors). Manual paste is the only ingestion path in v1. No official MCP servers exist for those boards and third party scrapers break their terms of service. The connector interface in ADR-0002 stays as a design note.
- Email verification and password reset. Simple email and password login. Real email flows arrive only if other people start using the app.
- PNG export. Not useful for ATS, adds test burden.
- Streaming responses for the tailor. A progress state is enough for v1.
- Dashboard counts and charts. The tracker is a flat list with status filters.

## Milestones

Weeks assume roughly 10 hours a week of developer time. AI can generate code far faster than the schedule, so these weeks reflect review and decision time, not typing time. If fewer hours are available, stretch the weeks rather than cut the work.

### M0: Setup (week 1)

- Frontend and backend scaffolding, repo structure, Vercel project with deploy on push, Neon database created and reachable from a backend function.
- Health check endpoint deployed to production.
- Done when: pushing to main deploys both apps and the database connection works from the deployed function, not just locally.

### M1: Tailoring spike (weeks 2 to 3)

- A command line tool, not a throwaway: resume JSON, pasted job description, prompt, into an LLM API, structured JSON out, rough PDF via fpdf2.
- Installed and used on real applications from this point on, until M6 replaces it.
- Time the calls. Confirm the worst case fits inside a 60 second Vercel function with margin, and set maxDuration on the route.
- Pick the LLM provider, record the real cost per call.
- Done when: output against three real job posts reads well enough to send without embarrassment, the cost per call is known, and the call fits the serverless limit.

### M2: Login and resume model (weeks 4 to 5)

- Sign up, login, logout. No email verification, no reset.
- Data model: users, resumes, sections, entries, resume versions. Versioning is designed now because diff and revert in M6 depend on it.
- Done when: register, login, and the versioned model is committed.

### M3: Resume builder and one template (weeks 6 to 9)

- Editor UI for the sections in FR-3: header, summary, experience, education, skills.
- Reorder entries, autosave.
- One ATS-safe template in React. Only one.
- Done when: a full resume can be built and seen in the template.

### M4: Export, PDF and DOCX (weeks 10 to 11)

- PDF drawn with fpdf2 from resume data.
- DOCX with python-docx, real Word heading and list styles.
- The test that matters: extract text from both files with standard tools and confirm reading order and content match the resume data. Public ATS checkers are not a reliable test.
- Done when: both formats export, open cleanly in Word and Google Docs, and the extraction test passes.

### M5: Job posts and tracker (weeks 12 to 13)

- Save a job post by paste: description, company, role, source, link.
- Flat list with statuses (interested, applied, interview, offer, rejected, closed), notes, timestamps, status filters.
- Done when: a job can be tracked from interested to closed.

### M6: Full tailoring flow (weeks 14 to 16)

- Pick a resume, pick a job post, write a prompt, get a tailored version. Productizes the CLI flow you have been using since week 2.
- Diff view against the base resume using the version model, with revert.
- Refusals for layout-breaking instructions, per ADR-0003.
- Metering set from the real cost per call measured in M1.
- Done when: tailoring, diff, revert, export, and application linkage all work in production.

### M7: Finish (weeks 17 to 18)

- Error handling, empty states, long resumes, unusual characters through the export path.
- Account deletion removes all user data.
- Secrets and logging checked in production.
- Done when: acceptance criteria below pass.

## Acceptance criteria for v1

1. You can sign up, log in, and build a complete resume with one ATS-safe template.
2. The resume exports to PDF and DOCX, opens in Word and Google Docs, and the text extraction test passes.
3. You can save a job post by pasting its description and track its status.
4. You can tailor a resume against a saved job post with a free text prompt, see a diff, revert changes, and export the result.
5. Each application record shows which resume version was used.
6. Account deletion removes all user data.
7. The app is deployed on Vercel, usable from a public URL.

## Risks

- Serverless timeout is the top technical risk. An LLM tailoring call can take 15 to 40 seconds and the Vercel Hobby limit is 60 seconds max. Measured in M1 and monitored. If calls stop fitting, the escape hatch in ADR-0005 is moving the FastAPI app to a traditional host without rewriting it.
- Cold starts on Vercel and database wake-up on Neon's free tier make the first request after idle slow. Expected behavior for v1, not a bug.
- Layout is implemented twice, once in React for the preview and once in fpdf2 for the PDF. Accept small drift, fix real drift.
- AI-assisted burnout has a different shape than the old kind: reviewing generated code and making continuous small decisions is tiring in a different way than writing code, and the schedule breakdown still shows only working blocks. Keep milestone boundaries as natural stopping points.
- AI output quality still gates the M1 exit criteria. If the tailoring spike disappoints, stop and rethink rather than schedule the rest around it.
- Meta risk: this project exists to support a job search, and it can quietly become a way to avoid one. The rule above already covers it, applications beat milestones in any conflict, but the risk is named here because it is the most likely way this project fails. Success is measured in real applications sent through the tool, not in features shipped.

## Deferred (not in v1)

- Job board ingestion, MCP connectors, board APIs (ADR-0002).
- Email verification and password reset.
- PNG export.
- Multiple templates, template previews.
- Public share links for resumes.
- Cover letter generation.

## Decisions recorded

See docs/adr/ for the stack, tailoring design, job post ingestion, export choices, and the Vercel deployment decision.
