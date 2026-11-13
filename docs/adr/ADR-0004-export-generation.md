# ADR-0004: Generate exports from resume data on the server

## Status

Accepted. Superseded in part by ADR-0005: the PDF is no longer generated from a HTML render, because that approach needs libraries that do not run in Vercel serverless functions. The core decision stands. Exports are generated server side from structured resume data, and DOCX via python-docx is unchanged. See ADR-0005 for the serverless constraints.

## Context

Users need PDF, DOCX, and PNG exports that look the same as the on-screen resume and survive ATS parsing. The choice is where and how to generate the files.

## Options considered

1. Client side export with browser print or JS libraries.
2. Server side generation from structured resume data.
3. Convert from one mastered format, such as DOCX first, then derive PDF and PNG from it.

## Decision

Server side generation from the resume data. PDF from a HTML render of the template, DOCX generated directly from the structured data with a document library, and PNG rendered from the same HTML template used for the PDF.

Reasons:

- Server side gives consistent output across browsers and devices. Browser print features vary and produce non-deterministic pagination and fonts.
- ATS systems parse DOCX and PDF text. Generating from structured data with proper heading and list styles gives predictable, parseable output. A resume converted image-first or from complex layouts breaks parsing.
- Reusing the template HTML for PDF and PNG keeps the visual result consistent with the editor preview.

## Consequences

- The template exists twice in effect: the React component for editing and preview, and a server side HTML version used for PDF and PNG. They must be kept in sync, and visual diffs against sample resumes are part of the export tests.
- DOCX generation uses a Python document library (for example python-docx) writing real Word styles, not an HTML-to-DOCX conversion.
- Server load for exports is modest but real, so exports are authenticated and rate limited per user.

## Amendment: ATS text fidelity (PDF fonts)

The first PDF implementation used the PDF core fonts (Helvetica), which are latin-1 only. Any character outside latin-1 was silently replaced with `?` before drawing. That destroyed exactly the text an ATS reads: `€`, `—`, `’`, and every accented name (`José`, `Müller`, `Zürich`). The file looked correct to a human because the glyphs that remained were fine, and the original export test passed because it only asserted ASCII content.

The PDF now embeds a subset of Arial (`app/fonts/ATS-Sans.ttf`, ~22 KB) covering Latin-1, Latin Extended-A, and common punctuation. Consequences:

- No system fonts are required at runtime, which matters because Vercel functions ship none.
- The subset is a generated artifact. Regenerate it with fontTools if the glyph coverage ever needs to grow; it is committed because the build has no font step.
- Tests extract text with pypdf, an independent parser, and assert that accented names, currency, and dashes survive. They were verified to fail against the old latin-1 path, so they are regression guards rather than assertions that happen to pass.
- The on-screen preview uses the same separators and date formatting as the exporter, because it promises to mirror the download.

Structural ATS properties are also asserted by tests: no tables, no images, no header or footer text, real Word heading and list styles, standard section headings, and no empty section headings.

## Amendment: the ATS check panel

### What changed

The resume editor now shows a live readiness score and a list of specific
issues (`web/src/ats.ts`, rendered by `AtsPanel` in `ResumeEditor.tsx`).

### Why

The layout is safe by construction, so the remaining reasons a resume gets
filtered are about *content*: no email, no skills, no numbers in any bullet,
a role with no dates. Users previously discovered these only after exporting
and uploading somewhere else. Surfacing them while editing is the difference
between a builder that produces a file and one that produces a file that
works.

### What it checks

Only things that map to real parser or recruiter behaviour, never style
preferences: missing name, email, or skills; an email that will not parse; no
summary; no roles; no quantified bullets; per-role missing company, role,
dates, or bullets; an over-long entry; missing education; links without a
scheme.

Each finding has a level (error, warning, tip) and states what to do about it.
The score is `100 - 25·errors - 8·warnings`, floored at zero. It is a
readiness signal, not a grade, and the panel says so.

### Consequences

- The checks are advisory. Nothing blocks an export, because the user may have
  a legitimate reason to send an unconventional resume, and blocking would be
  patronising.
- The score is computed in the browser from content already loaded, so it
  updates as you type with no request.
- A test asserts the panel is responsive rather than decorative: an empty
  resume scores 0 with five issues, and adding a name raises the score and
  removes that issue. A score that is always 100 would be worthless.
- The panel also lists the fixed layout guarantees, so the user can trust the
  export without having to verify it themselves.
