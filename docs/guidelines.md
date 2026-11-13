# Engineering guidelines

How we build TrackAJob. These are the rules that keep the app trustworthy, and
the reasoning behind each one, so a future change can decide whether it is
still the right rule.

Read `docs/eli5.md` first if you want the plain-language version. This file is
for people writing code.

---

## 1. The product promise

TrackAJob does two things, and everything else is supporting work:

1. **Track applications** so nothing is lost.
2. **Tailor a resume to a job post** without inventing anything.

A feature that does not serve one of those is out of scope, however nice it
looks. When in doubt, improve the two core flows rather than add a third.

**The trust rule.** The app makes claims about the user's career. A wrong
number, a fabricated bullet, or a resume that an ATS cannot read costs the
user a real opportunity. When correctness and polish conflict, correctness
wins, and the UI says so plainly instead of pretending.

---

## 2. Layout of the code

```
app/            FastAPI backend (one Vercel Function)
  routes/       HTTP endpoints, thin: validate, call, return
  scraper.py    job post extraction from a URL
  stats.py      application statistics + CSV
  tailoring.py  the LLM boundary and anti-fabrication checks
  exporters.py  PDF and DOCX generation
  schemas.py    request/response shapes (Pydantic)
  models.py     database tables (SQLAlchemy)
web/src/        React + TypeScript frontend
  router.ts     hash routes, one URL per screen
  ui.tsx        shared primitives (Button, Field, Dialog, Toast, ...)
  theme.tsx     light/dark theme, persisted
  ats.ts        resume readiness checks
  format.ts     all date and number formatting
  styles.css    design tokens + components
tests/          pytest, one file per area
docs/adr/       decision records
```

Rules:

- **Routes stay thin.** A route validates input, calls a module, and returns.
  Business logic lives in a module that can be tested without HTTP.
- **One source of truth per number.** The statistics endpoint computes once;
  the charts and the CSV both read that result. Never recompute a figure in
  the frontend.
- **No new dependency without a reason.** Every package is a supply-chain and
  cold-start cost. `beautifulsoup4` and `lxml` earn their place by parsing real
  job boards; a chart library would not, so the charts are hand-built.

---

## 3. Backend rules

### 3.1 Every endpoint is authenticated and scoped

Any endpoint touching user data goes through `Depends(get_current_user)` and
filters by `user_id`. A missing filter is a data leak between accounts, which
is the worst bug this app can have.

```python
jobs = db.execute(select(JobPost).where(JobPost.user_id == user.id)).scalars()
```

**Test it.** Every resource endpoint needs a test proving a second account
gets a 404, not the data. See `tests/test_jobs.py::test_users_cannot_see_or_touch_other_users_jobs`.

### 3.2 Errors are data, not stack traces

Return a message a person can act on. When the failure has a next step, send
it as a structured reason so the UI can give that step:

```python
raise HTTPException(
    status_code=422,
    detail={"reason": "javascript", "message": "Indeed loads job posts with JavaScript… Paste the description instead."},
)
```

The frontend unwraps `{reason, message}` in `detailToMessage` (`web/src/types.ts`).
A bare `HTTP 422` reaching a user is a bug.

### 3.3 Never scrape without a safety check

The scraper fetches URLs supplied by users, which makes it an SSRF surface.
`validate_url` must run on the original URL **and on every redirect hop**:

- only `http` and `https`;
- reject private, loopback, link-local, and reserved addresses;
- cap response size and time.

Scheme checks must happen *before* adding `https://`, otherwise
`file:///etc/passwd` becomes `https://file:///etc/passwd` and slips through.
This exact bug existed and is now covered by
`tests/test_scraper.py::test_unsafe_urls_are_rejected`.

### 3.4 Parsing is layered and honest

Job pages are read in this order: schema.org JSON-LD, Open Graph, site
selectors, generic heuristics. When nothing usable is found, **fail with an
explanation** rather than return a half-empty form. A shell page is detected
by how little text it contains.

### 3.5 The LLM never touches layout or facts

Tailoring may rephrase and reorder. It may not invent employers, dates,
technologies, or numbers. `tailoring.py` enforces this after the model
responds: bullets with no lexical or numeric support in the base resume are
removed and reported. Do not weaken these checks to make output look better.
An impressive lie is worse than a plain truth.

### 3.6 Exports must survive an ATS

This is a hard requirement, not a preference:

- single column, no tables, no text boxes, no images, no header/footer text;
- real Word heading and list styles in DOCX;
- standard section names (`SUMMARY`, `SKILLS`, `EXPERIENCE`, `EDUCATION`);
- **Unicode intact.** PDF text uses an embedded font subset, never the latin-1
  core fonts, which silently turn `€`, `—` and `José` into `?`.

Tests extract text back with `pypdf`, an independent parser, and assert the
content survives. A test that only checks ASCII does not prove an export is
readable.

### 3.7 Dates

Store naive UTC. In the frontend, `parseApiDate` in `format.ts` appends `Z`
before parsing, because a naive timestamp read as local time shows "3 hours
ago" for something saved a second earlier.

---

## 4. Frontend rules

### 4.1 State lives in the URL

Every screen is a route (`#/resumes/3`, `#/applications?status=applied&q=stripe`).
Filters and search go in the query string. Refresh, Back, Forward, and shared
links must all work. If a user can reach a state, they can bookmark it.

### 4.2 The theme is explicit

`<html data-theme="light|dark">`. **Light is the default for everyone**; we do
not follow the OS preference, because a user who has never chosen should get
the paper look. The choice is stored in `localStorage` and applied by an inline
script in `index.html` before first paint, so there is no flash.

All colour is a token in `styles.css`. Never hard-code a hex value in a
component, or dark mode breaks.

### 4.3 Accessibility is not optional

- Every control has a label. Icon-only buttons need `aria-label`.
- Async results announce themselves: toasts and save status use `aria-live`.
- Focus is always visible. Never `outline: none` without a replacement.
- Honour `prefers-reduced-motion`.
- Destructive actions confirm first.

### 4.4 Errors say what to do

`errorMessage()` turns any thrown value into a sentence. Inline validation sits
next to the field and focuses the first problem on submit. Never show a raw
status code or `[object Object]`.

### 4.5 Autosave must not lose work

The editor debounces saves, flushes on `pagehide` with `sendBeacon`, and warns
before leaving with unsaved changes. If you change this flow, test all three:
type and wait, type and close the tab, type and click Back.

---

## 5. Design rules

The look is "notebook and folder": paper surfaces, ruled lines, folder tabs,
index cards, serif headings, mono labels. Minimalist means nothing decorative
that does not carry meaning.

- **Every border marks a real boundary.** If a line does not separate
  something, remove it.
- **One accent colour.** Green ink for primary actions; status colours are the
  only other hues.
- **The resume preview is the exception.** It stays in plain Arial with no app
  chrome, because it must look exactly like the file the ATS receives. Making
  it pretty would make it a lie.
- **Motion is feedback, not decoration.** Transitions stay under 250 ms and
  communicate a state change.

### Type

Three families, each with one job:

| Token | Family | Used for |
| --- | --- | --- |
| `--font-display` | Bricolage Grotesque 600 | Page titles, card titles, stat numbers, dialog headings |
| `--font-ui` | Inter | Body text, labels, buttons |
| `--font-mono` | JetBrains Mono | Metadata: timestamps, counts, version tags, eyebrows |

**Readability beats character.** Titles originally used a high-contrast
display serif (Instrument Serif). It looked distinctive at page-title size but
its hairline strokes and small x-height made card titles *less* legible than
the body text beneath them, which is backwards. The replacement is a
grotesque with a large x-height and open apertures, set at weight 600 with
slightly negative tracking (`-0.02em` to `-0.025em`).

If you change the display face, check it at **card-title size (~1.2rem)**, not
just at page-title size. That is where display faces fail.

---

## 6. Testing

Run everything before committing:

```bash
.venv/Scripts/python.exe -m pytest -q      # backend
cd web && npx tsc --noEmit && npm run build # frontend
```

What to test, in priority order:

1. **Isolation** — one account cannot see another's data.
2. **The trust paths** — export text fidelity, anti-fabrication, statistics
   maths.
3. **Failure modes** — blocked boards, bad URLs, expired sessions.
4. **The happy path.**

**Prove a test can fail.** When fixing a bug, revert the fix and confirm the
new test goes red. A test that has never failed proves nothing. This was done
for the latin-1 PDF bug: four tests failed against the old code, then passed.

Use fixtures, not the live web. Job boards change markup and rate-limit; a
network test fails for reasons that are not your bug.

---

## 7. Git and review

- Commit messages explain **why**, not what. The diff already shows what.
- One logical change per commit.
- Never commit `.env`, `.env.local`, `.neon`, or a database file. Check
  `git status` before staging.
- Do not commit build output (`dist/`, `node_modules/`, `.venv/`).
- If you touch an architectural decision, update or add an ADR in the same
  change.

---

## 8. Decisions and where they live

| Area | Record |
| --- | --- |
| Stack | ADR-0001 |
| Job ingestion and scraping | ADR-0002 |
| Tailoring | ADR-0003 |
| Exports and ATS fidelity | ADR-0004 |
| Deployment | ADR-0005 |
| Database | ADR-0006 |
| Data model | ADR-0007 |
| Statistics | ADR-0008 |
| Theming and accessibility | ADR-0009 |

Write an ADR when a choice is expensive to reverse, affects more than one
area, or someone will later ask "why on earth is it done this way". State the
options you rejected and the reason, or the record is useless.
