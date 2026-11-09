# ADR-0001: Use Python/FastAPI backend with React frontend

## Status

Accepted

## Context

TrackAJob needs a web app with user accounts, private data, file generation, and calls to an LLM API for the tailoring feature. We need a stack the team can build fast and maintain without a large ops burden.

Python is already the preferred backend language. For the frontend, the user asked about React.

## Options considered

1. Python (FastAPI) + React SPA.
2. Python (Django) + templates, no separate frontend.
3. Python (FastAPI) + a lighter frontend library or plain JS.

## Decision

FastAPI for the backend, React with TypeScript for the frontend as a single page app, PostgreSQL for storage.

Reasons:

- FastAPI gives async support, which suits streaming LLM responses to the frontend, plus automatic OpenAPI docs and good validation with Pydantic.
- The resume builder and diff views need rich client state and interactivity. React handles this well and has the largest pool of components and documentation for editor style UIs.
- Django with server templates would slow down the editor and make streaming awkward.
- PostgreSQL over document stores because the data is relational (users, resumes, job posts, applications, versions) and the schema is clear.

## Consequences

- Two apps to deploy and maintain, with a defined REST API between them.
- The API contract comes from FastAPI's OpenAPI schema, so the frontend types can be generated from it.
- Sessions use a standard token or cookie scheme handled by the API, decided during M1.
