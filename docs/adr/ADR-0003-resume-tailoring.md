# ADR-0003: Tailor resumes with an LLM over structured content, never the layout

## Status

Accepted

## Context

The tailoring feature takes a free text prompt from the user, like "make this fit the job post" or "shorten it to one page", and rewrites the resume against a saved job description. Users will also type things that should not be applied, such as requests to lie about experience or to put the resume into a graphic layout.

## Options considered

1. Send the rendered resume (PDF or HTML) to the model and let it return a new rendered version.
2. Send the structured resume data (sections and entries as JSON) and return updated structured data.
3. Do keyword matching only, no generation.

## Decision

Option 2. The LLM receives the resume as structured data plus the job description plus the user prompt, and returns structured data in the same schema. The template stays the only thing that decides layout.

Reasons:

- Keeping content and layout separate is what makes the output ATS-safe. The model cannot break the layout because it never touches it.
- Structured input and output is easy to validate and diff. The diff view comes almost free.
- Keyword matching alone cannot reword a summary or reframe experience, which is the main value for users.
- Rendering the result ourselves means PDF, DOCX, and PNG exports all stay consistent.

## Consequences

- The prompt includes the resume schema and hard rules: no fabricated experience, no invented metrics, no layout instructions. Responses that fail schema validation are retried once, then rejected with a clear message.
- Prompt templates live in the backend and are versioned. Test prompts and golden resumes are kept in the repo to catch regressions.
- Requests are metered per user, since every tailoring call costs money.
- Every tailored version is stored and linked to the base resume and the job post, so the tracker can show which version was sent.
