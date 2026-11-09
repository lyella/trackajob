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
