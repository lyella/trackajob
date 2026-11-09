# ADR-0002: Job post ingestion with manual paste first and a connector layer for job boards

## Status

Accepted

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
