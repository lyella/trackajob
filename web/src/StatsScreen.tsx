import { useEffect, useMemo, useState } from 'react'
import { api, errorMessage } from './types'
import { Alert, Button, EmptyState, Loading, useToast } from './ui'

type Stats = {
  totals: {
    jobs: number
    active: number
    applied: number
    responded: number
    offers: number
    rejected: number
    response_rate: number
    offer_rate: number
    with_resume: number
  }
  by_status: { status: string; count: number }[]
  funnel: { stage: string; count: number; pct_of_top: number; pct_of_applied: number }[]
  sources: { source: string; count: number }[]
  companies: { company: string; count: number }[]
  weekly: { week_start: string; count: number }[]
  monthly_changes: { month: string; count: number }[]
}

const STATUS_LABEL: Record<string, string> = {
  interested: 'Interested',
  applied: 'Applied',
  interview: 'Interview',
  offer: 'Offer',
  rejected: 'Rejected',
  closed: 'Closed',
}

/** Formats a week-start date without assuming a locale-specific order. */
function weekLabel(iso: string): string {
  const d = new Date(`${iso}T00:00:00`)
  if (Number.isNaN(d.getTime())) return iso
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' }).format(d)
}

function monthLabel(key: string): string {
  const d = new Date(`${key}-01T00:00:00`)
  if (Number.isNaN(d.getTime())) return key
  return new Intl.DateTimeFormat(undefined, { month: 'short' }).format(d)
}

/* ---------------- Charts ---------------- */

/** Horizontal bars for the funnel. A single-series bar chart is the right
 * form here: the stages are ordered, so length reads as progression. */
function FunnelChart({ rows }: { rows: Stats['funnel'] }) {
  const max = Math.max(1, ...rows.map((r) => r.count))
  return (
    <ul className="chart-funnel" aria-label="Application funnel">
      {rows.map((row) => (
        <li key={row.stage}>
          <span className="chart-funnel-label">{STATUS_LABEL[row.stage] ?? row.stage}</span>
          <span className="chart-funnel-track">
            <span
              className="chart-funnel-fill"
              style={{ width: `${(row.count / max) * 100}%` }}
              aria-hidden="true"
            />
          </span>
          <span className="chart-funnel-value tabular">
            {row.count}
            <span className="muted"> · {row.pct_of_top}%</span>
          </span>
        </li>
      ))}
    </ul>
  )
}

/** Weekly activity as a column chart. Bars are drawn with CSS heights so
 * they stay crisp and inherit the theme. */
function WeeklyChart({ rows }: { rows: Stats['weekly'] }) {
  const max = Math.max(1, ...rows.map((r) => r.count))
  return (
    <figure className="chart-weekly">
      <div className="chart-weekly-bars" role="img" aria-label="Applications saved per week">
        {rows.map((row) => (
          <div className="chart-weekly-col" key={row.week_start}>
            <span
              className="chart-weekly-bar"
              data-empty={row.count === 0}
              style={{ height: row.count === 0 ? '0' : `${Math.max(4, (row.count / max) * 100)}%` }}
              title={`${weekLabel(row.week_start)}: ${row.count}`}
            />
            <span className="chart-weekly-value tabular">{row.count || ''}</span>
          </div>
        ))}
      </div>
      <figcaption className="chart-axis">
        <span>{weekLabel(rows[0]?.week_start ?? '')}</span>
        <span>Last 12 weeks</span>
        <span>{weekLabel(rows[rows.length - 1]?.week_start ?? '')}</span>
      </figcaption>
    </figure>
  )
}

/** Status distribution as a single stacked bar plus a legend. */
function StatusBar({ rows }: { rows: Stats['by_status'] }) {
  const total = rows.reduce((sum, r) => sum + r.count, 0)
  if (total === 0) return <p className="muted small">No applications yet.</p>
  return (
    <div className="chart-status">
      <div className="chart-status-bar" role="img" aria-label="Applications by current status">
        {rows
          .filter((r) => r.count > 0)
          .map((row) => (
            <span
              key={row.status}
              className={`chart-status-seg seg-${row.status}`}
              style={{ width: `${(row.count / total) * 100}%` }}
              title={`${STATUS_LABEL[row.status]}: ${row.count}`}
            />
          ))}
      </div>
      <ul className="chart-legend">
        {rows.map((row) => (
          <li key={row.status}>
            <span className={`chart-swatch seg-${row.status}`} aria-hidden="true" />
            {STATUS_LABEL[row.status]}
            <span className="tabular muted">{row.count}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Sources as horizontal bars, which handle long board names well. */
function SourcesChart({ rows }: { rows: Stats['sources'] }) {
  const max = Math.max(1, ...rows.map((r) => r.count))
  if (rows.length === 0) return <p className="muted small">No sources recorded yet.</p>
  return (
    <ul className="chart-sources">
      {rows.slice(0, 8).map((row) => (
        <li key={row.source}>
          <span className="chart-sources-label" title={row.source}>
            {row.source}
          </span>
          <span className="chart-sources-track">
            <span
              className="chart-sources-fill"
              style={{ width: `${(row.count / max) * 100}%` }}
              aria-hidden="true"
            />
          </span>
          <span className="chart-sources-value tabular">{row.count}</span>
        </li>
      ))}
    </ul>
  )
}

/** Six-month change trend as a sparkline, drawn with an SVG polyline. */
function TrendChart({ rows }: { rows: Stats['monthly_changes'] }) {
  const width = 260
  const height = 64
  const max = Math.max(1, ...rows.map((r) => r.count))
  const points = rows.map((row, i) => {
    const x = rows.length === 1 ? 0 : (i / (rows.length - 1)) * width
    const y = height - (row.count / max) * (height - 8) - 4
    return { x, y, row }
  })
  const path = points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
  return (
    <figure className="chart-trend">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="chart-trend-svg"
        role="img"
        aria-label="Status changes per month"
        preserveAspectRatio="none"
      >
        <polyline className="chart-trend-line" points={path} fill="none" />
        {points.map((p) => (
          <circle key={p.row.month} className="chart-trend-dot" cx={p.x} cy={p.y} r="2.5">
            <title>{`${monthLabel(p.row.month)}: ${p.row.count}`}</title>
          </circle>
        ))}
      </svg>
      <figcaption className="chart-axis">
        {rows.map((row) => (
          <span key={row.month}>{monthLabel(row.month)}</span>
        ))}
      </figcaption>
    </figure>
  )
}

/* ---------------- Screen ---------------- */

export function StatsScreen() {
  const toast = useToast()
  const [stats, setStats] = useState<Stats | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api<Stats>('/api/stats')
      .then(setStats)
      .catch((e) => setError(errorMessage(e)))
  }, [])

  const hasData = (stats?.totals.jobs ?? 0) > 0

  const headline = useMemo(() => {
    if (!stats) return []
    return [
      { label: 'Applications', value: stats.totals.jobs },
      { label: 'Active', value: stats.totals.active },
      { label: 'Response rate', value: `${stats.totals.response_rate}%` },
      { label: 'Interviews', value: stats.by_status.find((s) => s.status === 'interview')?.count ?? 0 },
      { label: 'Offers', value: stats.totals.offers },
    ]
  }, [stats])

  async function exportCsv() {
    try {
      const response = await fetch('/api/stats/export.csv')
      if (!response.ok) throw new Error(`Export failed (HTTP ${response.status})`)
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      const disposition = response.headers.get('content-disposition') ?? ''
      const match = /filename="([^"]+)"/.exec(disposition)
      a.href = url
      a.download = match?.[1] ?? 'trackajob-statistics.csv'
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
      toast('Statistics exported as CSV.', 'success')
    } catch (e) {
      toast(errorMessage(e), 'error')
    }
  }

  if (error) {
    return (
      <div className="page">
        <Alert tone="error">{error}</Alert>
      </div>
    )
  }

  if (!stats) return <Loading label="Loading statistics…" />

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <span className="eyebrow">Insights</span>
          <h1>Statistics</h1>
          <p>How your search is going, measured from the applications you have tracked.</p>
        </div>
        <div className="cluster">
          <Button onClick={() => window.print()} disabled={!hasData}>
            Print report
          </Button>
          <Button variant="primary" onClick={exportCsv} disabled={!hasData}>
            Export CSV
          </Button>
        </div>
      </div>

      {!hasData ? (
        <EmptyState glyph="▤" title="No data yet">
          Track a few applications and this page fills in: your funnel, where your
          applications come from, and how often you hear back.
        </EmptyState>
      ) : (
        <>
          <div className="stat-row">
            {headline.map((item) => (
              <div className="stat" key={item.label}>
                <div className="stat-value">{item.value}</div>
                <div className="stat-label">{item.label}</div>
              </div>
            ))}
          </div>

          <div className="chart-grid">
            <section className="panel chart-card chart-card-wide">
              <header className="chart-head">
                <h2>Funnel</h2>
                <span className="chart-note">Share of applications that reached each stage</span>
              </header>
              <FunnelChart rows={stats.funnel} />
            </section>

            <section className="panel chart-card">
              <header className="chart-head">
                <h2>Current status</h2>
              </header>
              <StatusBar rows={stats.by_status} />
            </section>

            <section className="panel chart-card">
              <header className="chart-head">
                <h2>Response rate</h2>
              </header>
              <div className="chart-gauge">
                <span className="chart-gauge-value tabular">{stats.totals.response_rate}%</span>
                <span className="chart-gauge-label">
                  {stats.totals.responded} of {stats.totals.applied} applications moved past
                  “applied”
                </span>
                <div className="chart-gauge-track">
                  <span
                    className="chart-gauge-fill"
                    style={{ width: `${Math.min(100, stats.totals.response_rate)}%` }}
                    aria-hidden="true"
                  />
                </div>
              </div>
            </section>

            <section className="panel chart-card chart-card-wide">
              <header className="chart-head">
                <h2>Applications saved per week</h2>
                <span className="chart-note">Last 12 weeks</span>
              </header>
              <WeeklyChart rows={stats.weekly} />
            </section>

            <section className="panel chart-card">
              <header className="chart-head">
                <h2>Where they come from</h2>
              </header>
              <SourcesChart rows={stats.sources} />
            </section>

            <section className="panel chart-card">
              <header className="chart-head">
                <h2>Status changes</h2>
                <span className="chart-note">Last 6 months</span>
              </header>
              <TrendChart rows={stats.monthly_changes} />
            </section>

            {stats.companies.length > 0 && (
              <section className="panel chart-card chart-card-wide">
                <header className="chart-head">
                  <h2>Most applied to</h2>
                </header>
                <ul className="chart-companies">
                  {stats.companies.map((row) => (
                    <li key={row.company}>
                      <span>{row.company}</span>
                      <span className="tabular muted">
                        {row.count} application{row.count === 1 ? '' : 's'}
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>
        </>
      )}
    </div>
  )
}
