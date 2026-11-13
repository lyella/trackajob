# ADR-0002: Job post ingestion with manual paste first and a connector layer for job boards

## Status

Accepted. Amended by "Amendment: link import" below, which adds server-side
scraping of a pasted URL as a convenience path. Manual paste remains the
guaranteed path and the fallback for every failure.

## Context

Users want to save job posts from LinkedIn, Indeed, JobStreet, and other boards. The requested direction was to get MCP (Model Context Protocol) servers for these boards and use them for ingestion.

The core problem: large job boards restrict scraping and automated access in their terms of service, and most do not offer public APIs for this use. Building v1 on automated imports from any specific board is risky. The product must work with no board integration at all.

## Options considered

1. Manual paste only.
2. Direct scraping per board.
3. MCP connector layer: standard connectors, including MCP servers where they exist and are permitted, behind one internal interface.
4. Board APIs where offered.

## Decision

Manual paste is the guaranteed path and ships first. Behind it we define a single connector interface, and each board gets a connector implementation that uses whatever that board permits: MCP servers when they exist and are allowed, official APIs where available, and nothing otherwise.

Reasons:

- Pasting a job description takes seconds and cannot break. It keeps v1 independent of third party terms.
- One connector interface means adding a board does not change the app. The MCP direction fits here as an implementation choice per board, not the architecture itself.
- Public MCP servers for job boards are young and change often. Treating them as replaceable connectors protects the app from that churn.

## Consequences

- The job post model stores source and link regardless of how the post arrived.
- Each connector declares what it needs from the user (for example an API key for an MCP server or board API) and reports clearly when it cannot fetch a post.
- Before building any board connector, we check that board's terms and document the check in this file.
- Marketing should not promise automatic import from specific boards in v1.

## Amendment: link import

### What changed

Users can now paste a job post URL and the server fetches and parses it,
prefilling the add-job form. This is a convenience path layered on top of
manual paste, not a replacement for it.

### Why

Paste-a-link was the single most requested convenience, and it can be built
without committing to any board's terms: the user opens the page themselves
and supplies the URL, which is the same act as copying the text by hand. We
fetch one page the user is already looking at, at their request, once.

### How it works

`app/scraper.py` reads a page in order of reliability:

1. schema.org `JobPosting` JSON-LD. LinkedIn, Kalibrr, Greenhouse and most
   modern career sites publish this for Google Jobs, so it is the most stable
   source and the one that survives markup changes.
2. Open Graph and meta tags for title and company.
3. Site-specific selectors for LinkedIn, Indeed, JobStreet, Kalibrr, Glassdoor.
4. Generic heuristics, then the `<title>` pattern (`"… Job Openings at Acme"`).

Nothing is saved automatically. The scrape only fills the form, so the user
reviews and confirms. A bad parse cannot pollute the tracker.

### Security: this is an SSRF surface

The server fetches a URL chosen by a user, which is a classic way to reach
internal services. Mitigations, all enforced in `validate_url` and
`fetch_html`:

- only `http` and `https`, checked **before** a missing scheme is defaulted to
  `https://` (otherwise `file:///etc/passwd` becomes
  `https://file:///etc/passwd` and passes);
- DNS resolution is checked against private, loopback, link-local and reserved
  ranges;
- redirects are followed manually, re-validating **every hop**;
- responses are capped at 3 MB and 12 seconds;
- only HTML and XML content types are accepted.

Covered by `tests/test_scraper.py::test_unsafe_urls_are_rejected`.

### Known limits, measured

Tested against live pages while building this:

| Board | Result |
| --- | --- |
| LinkedIn | Works. Full description via JSON-LD. |
| Kalibrr | Works. Description and company. |
| Greenhouse | Works. |
| JobStreet | Blocked, HTTP 403 (Cloudflare challenge). |
| Indeed | Blocked, HTTP 401 (bot challenge). |

Boards that require JavaScript or a bot challenge cannot be read by a plain
HTTP client. When that happens the API returns a `reason` and a message that
names the board and tells the user to paste the description. The UI shows that
message verbatim. **We never return a half-empty form and call it success.**

The bookmarklet remains available as a second path for pages the server cannot
fetch, because it runs in the user's own browser session.

### Consequences

- `beautifulsoup4` and `lxml` are now runtime dependencies.
- A scrape can take up to 12 seconds, which fits the 60 second function limit
  but is slow enough that the UI must show progress. It does.
- If a board changes its markup, the JSON-LD path usually still works. The
  selector path is the fragile one and is the last resort.
- Terms of service still matter. This fetches one page at a user's explicit
  request; it is not crawling, and it must not become crawling. Any future
  batch or scheduled import needs a fresh terms review recorded here.
