# ADR-0008: Application statistics are computed server side from history

## Status

Accepted

## Context

The tracker shows a list of applications. Users want to know how the search is
going: how many went out, how many got replies, where they came from, and
whether things are improving.

Two questions had to be settled: where the numbers are computed, and what each
number means.

## Options considered

1. Compute in the frontend from the job list it already has.
2. Compute server side in a dedicated endpoint.
3. Store precomputed counters, updated on every write.

## Decision

Option 2. `app/stats.py` computes everything from the job rows on request, and
`GET /api/stats` returns one fixed shape. The charts and the CSV export both
read that same result.

Reasons:

- **One source of truth.** If the frontend computed its own numbers and the
  CSV computed its own, a chart and a spreadsheet could disagree, and nobody
  would know which to believe.
- **The definitions are subtle enough to deserve tests.** "Reached a stage" is
  not the same as "is currently in that stage". That logic belongs where it
  can be unit tested, not in a component.
- **Option 1 breaks down.** The frontend only loads a filtered page of jobs in
  future, and history parsing would be duplicated in TypeScript.
- **Option 3 is premature.** Counters drift when a row is edited or deleted,
  and this data set is small enough that counting is instant.

## The definitions, stated once

These are the contract. Any change to them is a change to this ADR.

- **Funnel stage.** Counted if the stage appears *anywhere* in the status
  history, not only as the current status. An application that went applied →
  interview → rejected still counts as having reached "applied". Otherwise the
  funnel shrinks whenever you get bad news, which is both wrong and
  demoralising.
- **`pct_of_top`.** A stage's share of everything tracked, so the first stage
  is 100% and later stages read as retention. An earlier version divided by
  "applied", which made the first stage show 300%. Percentages are now
  asserted to stay within 0–100.
- **Response rate.** Of the applications actually sent (history contains
  "applied"), the share that moved past "applied".
- **Active.** Current status is applied, interview, or offer.

## Consequences

- The endpoint returns a fixed shape with zeroed arrays for a new account, so
  the frontend never has to special-case a missing key.
- The CSV is generated from the same dict as the charts, so it cannot drift.
- Charts are hand-built SVG and CSS, not a chart library. A library would add
  ~100 KB to the bundle for six simple charts, and would not follow the theme
  tokens. The tradeoff is that new chart types cost more to build.
- Statistics are computed per request. At this scale that is microseconds. If
  a user ever has thousands of applications, cache the result per user and
  invalidate on write.
- The print stylesheet strips app chrome so "Print report" produces a clean
  PDF from the browser. This is the export path for a human-readable report;
  CSV is the path for further analysis.
