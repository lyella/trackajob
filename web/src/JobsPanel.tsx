import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { api, errorMessage, ResumeContent, ResumeOut } from './types'
import { DiffView } from './DiffView'
import { bookmarkletUrl } from './bookmarklet'
import {
  formatDateTime,
  formatNumber,
  formatUsd,
  hostnameOf,
  jobHeading,
  normalizeUrl,
  relativeTime,
} from './format'
import {
  Alert,
  Button,
  ConfirmDialog,
  EmptyState,
  Field,
  Loading,
  STATUSES,
  STATUS_LABELS,
  StatusPill,
  useDebounced,
  useToast,
  type JobStatus,
} from './ui'

type JobStatusEntry = { status: string; at: string }
export type Job = {
  id: number
  title: string
  company: string
  source: string
  url: string
  description: string
  status: JobStatus
  notes: string
  status_history: JobStatusEntry[]
  resume_version_id: number | null
  sent_resume: string | null
  created_at: string
  updated_at: string
}

type TailorResponse = {
  resume_id: number
  base_version: number
  base_content: ResumeContent
  version: number
  version_id: number
  content: ResumeContent
  warnings: string[]
  notes: string
  tokens_in: number
  tokens_out: number
  cost_usd: number
}

const emptyForm = {
  title: '',
  company: '',
  source: '',
  url: '',
  description: '',
  notes: '',
  status: 'interested' as JobStatus,
}

const PROMPT_SUGGESTIONS = [
  'Emphasize backend and API work',
  'Rewrite the summary for this role',
  'Shorten to one page',
  'Lead with measurable impact',
]

function lastTouched(job: Job): string {
  const history = job.status_history
  return history.length > 0 ? history[history.length - 1].at : job.updated_at
}

export function JobsPanel({
  resumes,
  pendingImport,
  onImportConsumed,
  statusFilter,
  search,
  focusJobId,
  onQueryChange,
}: {
  resumes: ResumeOut[]
  pendingImport: Record<string, string> | null
  onImportConsumed: () => void
  statusFilter?: string
  search: string
  focusJobId?: number
  onQueryChange: (patch: Partial<{ status?: string; q?: string; job?: number }>) => void
}) {
  const toast = useToast()
  const [jobs, setJobs] = useState<Job[] | null>(null)
  const [loadError, setLoadError] = useState('')
  const [form, setForm] = useState(emptyForm)
  const [formError, setFormError] = useState('')
  const [adding, setAdding] = useState(false)
  const [addOpen, setAddOpen] = useState(false)
  const [deleting, setDeleting] = useState<Job | null>(null)
  const [deleteBusy, setDeleteBusy] = useState(false)
  const [editing, setEditing] = useState<Job | null>(null)

  const [tailorJobId, setTailorJobId] = useState<number | null>(null)
  const [tailorResumeId, setTailorResumeId] = useState<number | null>(null)
  const [prompt, setPrompt] = useState('')
  const [tailorError, setTailorError] = useState('')
  // Explicit in-flight flag. Deriving "busy" from result/error state left the
  // button spinning forever whenever the request was never sent.
  const [tailoringJobId, setTailoringJobId] = useState<number | null>(null)
  const [tailorResult, setTailorResult] = useState<TailorResponse | null>(null)
  const [tailorResultJob, setTailorResultJob] = useState<number | null>(null)

  const [copied, setCopied] = useState(false)
  const bmRef = useRef<HTMLAnchorElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  const filter = (statusFilter ?? 'all') as JobStatus | 'all'
  const debouncedSearch = useDebounced(search, 150)

  // React blocks javascript: URLs in JSX hrefs (a security measure), so the
  // drag handle gets its URL attached natively after mount; clicking the
  // handle copies the code with instructions instead.
  useEffect(() => {
    bmRef.current?.setAttribute('href', bookmarkletUrl(window.location.origin))
  }, [])

  useEffect(() => {
    if (resumes.length > 0 && tailorResumeId == null) setTailorResumeId(resumes[0].id)
  }, [resumes, tailorResumeId])

  const loadJobs = useRef(async () => {
    try {
      setJobs(await api<Job[]>('/api/jobs'))
      setLoadError('')
    } catch (e) {
      setLoadError(errorMessage(e))
      setJobs([])
    }
  })

  useEffect(() => {
    void loadJobs.current()
  }, [])

  // Bookmarklet handoff: App.tsx collects the scraped job from the opener
  // window (messages are only accepted while the #importing hash is set),
  // and this effect consumes it once, prefilling the add form.
  useEffect(() => {
    if (!pendingImport) return
    const j = pendingImport
    const host = hostnameOf(j.url || '')
    setForm({
      title: (j.title || '').slice(0, 200),
      company: (j.company || '').slice(0, 150),
      source: (host.split('.')[0] || 'paste').slice(0, 80),
      url: (j.url || '').slice(0, 500),
      description: (j.description || '').slice(0, 50000),
      notes: '',
      status: 'interested',
    })
    setAddOpen(true)
    onImportConsumed()
    toast('Job details imported. Check them and save.', 'success')
    window.setTimeout(() => {
      document.getElementById('add-job-title')?.focus()
    }, 50)
  }, [pendingImport, onImportConsumed, toast])

  // Deep link to one job: open its tailor panel and scroll it into view.
  useEffect(() => {
    if (!focusJobId || !jobs) return
    const job = jobs.find((j) => j.id === focusJobId)
    if (!job) return
    setTailorJobId(focusJobId)
    window.setTimeout(() => {
      document.getElementById(`job-${focusJobId}`)?.scrollIntoView({ block: 'center' })
    }, 60)
  }, [focusJobId, jobs])

  async function copyBookmarklet() {
    try {
      await navigator.clipboard.writeText(bookmarkletUrl(window.location.origin))
      setCopied(true)
      toast('Bookmarklet copied. Paste it as the URL of a new bookmark.', 'success')
      window.setTimeout(() => setCopied(false), 4000)
    } catch {
      toast('Could not copy. Drag the button to your bookmarks bar instead.', 'error')
    }
  }

  async function addJob(e: FormEvent) {
    e.preventDefault()
    if (!form.title.trim()) {
      setFormError('A role title is required.')
      document.getElementById('add-job-title')?.focus()
      return
    }
    setAdding(true)
    setFormError('')
    try {
      const created = await api<Job>('/api/jobs', {
        method: 'POST',
        body: JSON.stringify({ ...form, url: normalizeUrl(form.url) }),
      })
      setJobs((js) => [created, ...(js ?? [])])
      setForm(emptyForm)
      setAddOpen(false)
      toast(`Saved “${jobHeading(created.title, created.company)}”.`, 'success')
      onQueryChange({ status: 'all', job: undefined })
    } catch (err) {
      setFormError(errorMessage(err))
    } finally {
      setAdding(false)
    }
  }

  async function patch(id: number, data: Partial<Job>): Promise<Job | null> {
    try {
      const updated = await api<Job>(`/api/jobs/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      })
      setJobs((js) => (js ?? []).map((j) => (j.id === id ? updated : j)))
      return updated
    } catch (e) {
      toast(errorMessage(e), 'error')
      return null
    }
  }

  async function confirmDelete() {
    if (!deleting) return
    setDeleteBusy(true)
    try {
      await api(`/api/jobs/${deleting.id}`, { method: 'DELETE' })
      setJobs((js) => (js ?? []).filter((j) => j.id !== deleting.id))
      toast('Application deleted.', 'success')
      setDeleting(null)
    } catch (e) {
      toast(errorMessage(e), 'error')
    } finally {
      setDeleteBusy(false)
    }
  }

  async function runTailor(jobId: number) {
    if (tailorResumeId == null) {
      setTailorError('Choose a resume to tailor first.')
      return
    }
    setTailorError('')
    setTailorResult(null)
    setTailorResultJob(jobId)
    setTailoringJobId(jobId)
    try {
      const r = await api<TailorResponse>(`/api/resumes/${tailorResumeId}/tailor`, {
        method: 'POST',
        body: JSON.stringify({ job_id: jobId, prompt }),
      })
      setTailorResult(r)
      toast(`Tailored version ${r.version} is ready.`, 'success')
    } catch (e) {
      setTailorError(errorMessage(e))
      setTailorResult(null)
    } finally {
      setTailoringJobId(null)
    }
  }

  async function markAppliedWith(job: Job, versionId: number, version: number) {
    const updated = await patch(job.id, { status: 'applied', resume_version_id: versionId })
    if (updated) {
      toast(`Marked applied with version ${version}.`, 'success')
      setTailorResult(null)
      setTailorResultJob(null)
      setTailorJobId(null)
    }
  }

  async function revertTailored(resumeId: number, baseVersion: number) {
    try {
      await api(`/api/resumes/${resumeId}/revert`, {
        method: 'POST',
        body: JSON.stringify({ version: baseVersion }),
      })
      toast(`Reverted to version ${baseVersion}.`, 'success')
      setTailorResult(null)
      setTailorResultJob(null)
    } catch (e) {
      toast(errorMessage(e), 'error')
    }
  }

  const counts = useMemo(() => {
    const base: Record<string, number> = { all: jobs?.length ?? 0 }
    for (const s of STATUSES) base[s] = 0
    for (const j of jobs ?? []) base[j.status] = (base[j.status] ?? 0) + 1
    return base
  }, [jobs])

  const shown = useMemo(() => {
    const q = debouncedSearch.trim().toLowerCase()
    return (jobs ?? []).filter((j) => {
      if (filter !== 'all' && j.status !== filter) return false
      if (!q) return true
      return [j.title, j.company, j.source, j.notes, j.description]
        .join(' ')
        .toLowerCase()
        .includes(q)
    })
  }, [jobs, filter, debouncedSearch])

  const activeCount = counts.applied + counts.interview + counts.offer
  const isEmpty = jobs !== null && jobs.length === 0

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Applications</h1>
          <p>Every job you are tracking, with the resume version you sent.</p>
        </div>
        <Button
          variant="primary"
          onClick={() => {
            // Open, never toggle: closing a half-filled form from the header
            // is a surprise. The panel has its own Close control.
            setAddOpen(true)
            window.setTimeout(() => document.getElementById('add-job-title')?.focus(), 50)
          }}
        >
          Add job post
        </Button>
      </div>

      {!isEmpty && (
        <div className="stat-row">
          <div className="stat">
            <div className="stat-value">{counts.all}</div>
            <div className="stat-label">Tracked</div>
          </div>
          <div className="stat">
            <div className="stat-value">{activeCount}</div>
            <div className="stat-label">Active</div>
          </div>
          <div className="stat">
            <div className="stat-value">{counts.interview}</div>
            <div className="stat-label">Interviewing</div>
          </div>
          <div className="stat">
            <div className="stat-value">{counts.offer}</div>
            <div className="stat-label">Offers</div>
          </div>
        </div>
      )}

      <details
        className="card add-panel"
        open={addOpen}
        onToggle={(e) => setAddOpen(e.currentTarget.open)}
        id="add-job"
      >
        <summary>
          Add a job post
          <Button
            size="sm"
            variant="ghost"
            className="btn-fit add-panel-close"
            onClick={(e) => {
              // The summary itself toggles; keep this click from re-opening it.
              e.preventDefault()
              e.stopPropagation()
              setAddOpen(false)
            }}
          >
            Close
          </Button>
        </summary>
        <form className="add-form" onSubmit={addJob} noValidate>
          <div className="bookmarklet-box">
            <p>
              <strong>Save jobs in one click.</strong> Drag the button below to your bookmarks
              bar (show it with Ctrl+Shift+B), open a job on LinkedIn, Indeed, JobStreet or any
              career site, then click the bookmark.
            </p>
            <a
              ref={bmRef}
              className="bookmarklet-link"
              onClick={(e) => {
                e.preventDefault()
                void copyBookmarklet()
              }}
              title="Drag me to your bookmarks bar. Clicking copies the code instead."
            >
              <span aria-hidden="true">＋</span> Save to TrackAJob
            </a>
            <p className="muted">
              {copied
                ? 'Copied. Create a new bookmark and paste it as the URL.'
                : 'Prefer not to drag? Click the button to copy the code, then add a bookmark and paste it as the URL.'}
            </p>
          </div>

          <div className="field-grid">
            <Field label="Role title" error={formError && !form.title.trim() ? formError : undefined}>
              {(p) => (
                <input
                  {...p}
                  id="add-job-title"
                  value={form.title}
                  onChange={(e) => setForm({ ...form, title: e.target.value })}
                  placeholder="Backend Developer…"
                  maxLength={200}
                  required
                />
              )}
            </Field>
            <Field label="Company">
              {(p) => (
                <input
                  {...p}
                  value={form.company}
                  onChange={(e) => setForm({ ...form, company: e.target.value })}
                  placeholder="Acme Inc…"
                  maxLength={150}
                />
              )}
            </Field>
            <Field label="Source">
              {(p) => (
                <input
                  {...p}
                  value={form.source}
                  onChange={(e) => setForm({ ...form, source: e.target.value })}
                  placeholder="LinkedIn, referral…"
                  maxLength={80}
                  list="job-sources"
                />
              )}
            </Field>
            <datalist id="job-sources">
              <option value="LinkedIn" />
              <option value="Indeed" />
              <option value="JobStreet" />
              <option value="Referral" />
              <option value="Company site" />
            </datalist>
            <Field label="Status">
              {(p) => (
                <select
                  {...p}
                  value={form.status}
                  onChange={(e) => setForm({ ...form, status: e.target.value as JobStatus })}
                >
                  {STATUSES.map((s) => (
                    <option key={s} value={s}>
                      {STATUS_LABELS[s]}
                    </option>
                  ))}
                </select>
              )}
            </Field>
          </div>

          <Field label="Link" hint="Optional. Used for the “open posting” link.">
            {(p) => (
              <input
                {...p}
                type="url"
                value={form.url}
                onChange={(e) => setForm({ ...form, url: e.target.value })}
                placeholder="https://…"
                maxLength={500}
              />
            )}
          </Field>

          <Field
            label="Job description"
            hint="Paste the full post. Tailoring works from this text, so more detail is better."
          >
            {(p) => (
              <textarea
                {...p}
                rows={6}
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                placeholder="Paste the full job post here…"
                maxLength={50000}
              />
            )}
          </Field>

          {formError && form.title.trim() && <Alert tone="error">{formError}</Alert>}

          <div className="cluster">
            <Button type="submit" variant="primary" loading={adding}>
              {adding ? 'Saving…' : 'Save job'}
            </Button>
            <Button
              onClick={() => {
                setForm(emptyForm)
                setFormError('')
              }}
              disabled={adding}
            >
              Clear
            </Button>
          </div>
        </form>
      </details>

      {loadError && <Alert tone="error">{loadError}</Alert>}

      {jobs === null ? (
        <Loading label="Loading applications…" />
      ) : isEmpty ? (
        <EmptyState
          glyph="💼"
          title="No applications yet"
          action={
            <Button variant="primary" onClick={() => setAddOpen(true)}>
              Add your first job post
            </Button>
          }
        >
          Save a job post, track its status from interested to offer, and tailor your resume
          against it in one place.
        </EmptyState>
      ) : (
        <>
          <div className="toolbar">
            <div className="search">
              <span className="search-glyph" aria-hidden="true">
                ⌕
              </span>
              <input
                ref={searchRef}
                type="search"
                value={search}
                onChange={(e) => onQueryChange({ q: e.target.value || undefined })}
                placeholder="Search role, company, notes…"
                aria-label="Search applications"
              />
            </div>
            <div className="filter-chips" role="group" aria-label="Filter by status">
              <button
                type="button"
                className="chip-btn"
                aria-pressed={filter === 'all'}
                onClick={() => onQueryChange({ status: undefined })}
              >
                All <span className="chip-count">{counts.all}</span>
              </button>
              {STATUSES.map((s) => (
                <button
                  key={s}
                  type="button"
                  className="chip-btn"
                  aria-pressed={filter === s}
                  onClick={() => onQueryChange({ status: s })}
                >
                  {STATUS_LABELS[s]} <span className="chip-count">{counts[s]}</span>
                </button>
              ))}
            </div>
          </div>

          {shown.length === 0 ? (
            <EmptyState
              glyph="⌕"
              title="No matching applications"
              action={
                <Button
                  onClick={() => {
                    onQueryChange({ status: undefined, q: undefined })
                  }}
                >
                  Clear filters
                </Button>
              }
            >
              Nothing matches this search and filter combination.
            </EmptyState>
          ) : (
            <div className="job-list">
              {shown.map((j) => {
                const tailoring = tailorJobId === j.id
                const result = tailorResultJob === j.id ? tailorResult : null
                return (
                  <article
                    key={j.id}
                    id={`job-${j.id}`}
                    className={`job-card status-${j.status}`}
                    aria-labelledby={`job-${j.id}-title`}
                  >
                    <div className="job-head">
                      <div className="job-heading">
                        <div className="job-title" id={`job-${j.id}-title`}>
                          {j.title}
                        </div>
                        <div className="job-sub">
                          {j.company && <span>{j.company}</span>}
                          {j.company && j.source && (
                            <span className="sep" aria-hidden="true">
                              ·
                            </span>
                          )}
                          {j.source && <span className="muted">via {j.source}</span>}
                          <StatusPill status={j.status} />
                        </div>
                      </div>

                      <div className="job-actions">
                        <label className="sr-only" htmlFor={`status-${j.id}`}>
                          Status for {jobHeading(j.title, j.company)}
                        </label>
                        <select
                          id={`status-${j.id}`}
                          value={j.status}
                          onChange={(e) => {
                            const next = e.target.value as JobStatus
                            void patch(j.id, { status: next }).then((u) => {
                              if (u) toast(`Moved to ${STATUS_LABELS[next].toLowerCase()}.`, 'success')
                            })
                          }}
                        >
                          {STATUSES.map((s) => (
                            <option key={s} value={s}>
                              {STATUS_LABELS[s]}
                            </option>
                          ))}
                        </select>
                        <Button
                          size="sm"
                          variant={tailoring ? 'primary' : 'default'}
                          onClick={() => {
                            setTailorResult(null)
                            setTailorResultJob(null)
                            setTailorError('')
                            setTailorJobId(tailoring ? null : j.id)
                          }}
                          aria-expanded={tailoring}
                        >
                          {tailoring ? 'Close tailor' : 'Tailor resume'}
                        </Button>
                        <Button size="sm" onClick={() => setEditing(j)}>
                          Edit
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          iconOnly
                          aria-label={`Delete ${jobHeading(j.title, j.company)}`}
                          onClick={() => setDeleting(j)}
                        >
                          🗑
                        </Button>
                      </div>
                    </div>

                    <div className="job-meta">
                      <span title={formatDateTime(lastTouched(j))}>
                        Updated {relativeTime(lastTouched(j))}
                      </span>
                      {j.sent_resume && (
                        <>
                          <span className="sep" aria-hidden="true">
                            ·
                          </span>
                          <span className="sent-resume" title="Resume version sent">
                            📎 {j.sent_resume}
                          </span>
                        </>
                      )}
                      {j.url && (
                        <>
                          <span className="sep" aria-hidden="true">
                            ·
                          </span>
                          <a
                            className="job-link"
                            href={normalizeUrl(j.url)}
                            target="_blank"
                            rel="noreferrer noopener"
                            title={j.url}
                          >
                            {hostnameOf(j.url) || j.url} ↗
                          </a>
                        </>
                      )}
                    </div>

                    {tailoring && (
                      <div className="tailor-panel">
                        {resumes.length === 0 ? (
                          <Alert tone="warn">
                            You need a resume first. Create one on the Resumes tab, then come
                            back to tailor it against this post.
                          </Alert>
                        ) : (
                          <>
                            <div className="tailor-controls">
                              <Field label="Resume" className="">
                                {(p) => (
                                  <select
                                    {...p}
                                    value={tailorResumeId ?? ''}
                                    onChange={(e) => setTailorResumeId(Number(e.target.value))}
                                  >
                                    {resumes.map((r) => (
                                      <option key={r.id} value={r.id}>
                                        {r.name} (v{r.latest_version})
                                      </option>
                                    ))}
                                  </select>
                                )}
                              </Field>
                              <Field
                                label="Instruction"
                                className="field-prompt"
                                hint="Optional. Leave blank to tailor against the job post alone."
                              >
                                {(p) => (
                                  <input
                                    {...p}
                                    value={prompt}
                                    onChange={(e) => setPrompt(e.target.value)}
                                    placeholder="e.g. emphasize backend work…"
                                    maxLength={2000}
                                  />
                                )}
                              </Field>
                              <Button
                                variant="primary"
                                loading={tailoringJobId === j.id}
                                disabled={tailorResumeId == null || tailoringJobId !== null}
                                onClick={() => void runTailor(j.id)}
                              >
                                {tailoringJobId === j.id ? 'Tailoring…' : 'Tailor resume'}
                              </Button>
                            </div>

                            <div className="cluster" style={{ gap: '0.35rem' }}>
                              <span className="small muted">Try:</span>
                              {PROMPT_SUGGESTIONS.map((s) => (
                                <button
                                  key={s}
                                  type="button"
                                  className="chip-btn"
                                  onClick={() => setPrompt(s)}
                                >
                                  {s}
                                </button>
                              ))}
                            </div>

                            {tailorError && <Alert tone="error">{tailorError}</Alert>}

                            {result && (
                              <div className="tailor-result">
                                <div className="tailor-summary">
                                  <span>
                                    v{result.base_version} → v{result.version}
                                  </span>
                                  <span>
                                    {formatNumber(result.tokens_in)} in /{' '}
                                    {formatNumber(result.tokens_out)} out
                                  </span>
                                  <span>{formatUsd(result.cost_usd)}</span>
                                </div>
                                {result.notes && <Alert tone="info">{result.notes}</Alert>}
                                {result.warnings.map((w, i) => (
                                  <Alert tone="warn" key={i}>
                                    {w}
                                  </Alert>
                                ))}
                                <DiffView before={result.base_content} after={result.content} />
                                <div className="cluster">
                                  <a
                                    className="btn btn-sm"
                                    href={`/api/resumes/${result.resume_id}/export/pdf?version=${result.version}`}
                                    download
                                  >
                                    Export PDF
                                  </a>
                                  <a
                                    className="btn btn-sm"
                                    href={`/api/resumes/${result.resume_id}/export/docx?version=${result.version}`}
                                    download
                                  >
                                    Export DOCX
                                  </a>
                                  <Button
                                    size="sm"
                                    variant="primary"
                                    onClick={() =>
                                      void markAppliedWith(j, result.version_id, result.version)
                                    }
                                  >
                                    Mark applied with v{result.version}
                                  </Button>
                                  <Button
                                    size="sm"
                                    onClick={() =>
                                      void revertTailored(result.resume_id, result.base_version)
                                    }
                                  >
                                    Revert to v{result.base_version}
                                  </Button>
                                </div>
                              </div>
                            )}
                          </>
                        )}
                      </div>
                    )}

                    <label className="sr-only" htmlFor={`notes-${j.id}`}>
                      Notes for {jobHeading(j.title, j.company)}
                    </label>
                    <textarea
                      id={`notes-${j.id}`}
                      className="job-notes"
                      placeholder="Notes: recruiter name, next step, salary talk…"
                      rows={2}
                      defaultValue={j.notes}
                      onBlur={(e) => {
                        if (e.target.value !== j.notes) {
                          void patch(j.id, { notes: e.target.value }).then((u) => {
                            if (u) toast('Notes saved.', 'success')
                          })
                        }
                      }}
                    />

                    {j.description && (
                      <details className="job-desc">
                        <summary>Job description</summary>
                        <pre>{j.description}</pre>
                      </details>
                    )}

                    {j.status_history.length > 1 && (
                      <ul className="status-history" aria-label="Status history">
                        {j.status_history.map((h, i) => (
                          <li key={i} title={formatDateTime(h.at)}>
                            {STATUS_LABELS[h.status as JobStatus] ?? h.status}{' '}
                            <span className="muted">{relativeTime(h.at)}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </article>
                )
              })}
            </div>
          )}
        </>
      )}

      <ConfirmDialog
        open={deleting !== null}
        title="Delete this application?"
        confirmLabel="Delete"
        busy={deleteBusy}
        onCancel={() => setDeleting(null)}
        onConfirm={confirmDelete}
      >
        <p>
          <strong>{deleting ? jobHeading(deleting.title, deleting.company) : ''}</strong> and its
          notes and status history will be permanently deleted. The resume itself is not
          affected.
        </p>
      </ConfirmDialog>

      <EditJobDialog
        job={editing}
        onCancel={() => setEditing(null)}
        onSave={async (data) => {
          if (!editing) return
          const updated = await patch(editing.id, data)
          if (updated) {
            toast('Application updated.', 'success')
            setEditing(null)
          }
        }}
      />
    </div>
  )
}

function EditJobDialog({
  job,
  onCancel,
  onSave,
}: {
  job: Job | null
  onCancel: () => void
  onSave: (data: Partial<Job>) => Promise<void>
}) {
  const [draft, setDraft] = useState({ title: '', company: '', source: '', url: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (job) {
      setDraft({ title: job.title, company: job.company, source: job.source, url: job.url })
      setError('')
    }
  }, [job])

  async function submit() {
    if (!draft.title.trim()) {
      setError('A role title is required.')
      return
    }
    setBusy(true)
    try {
      await onSave({ ...draft, url: normalizeUrl(draft.url) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <ConfirmDialog
      open={job !== null}
      title="Edit application"
      confirmLabel="Save changes"
      tone="primary"
      busy={busy}
      onCancel={onCancel}
      onConfirm={submit}
    >
      <Field label="Role title" error={error || undefined}>
        {(p) => (
          <input
            {...p}
            value={draft.title}
            onChange={(e) => setDraft({ ...draft, title: e.target.value })}
            maxLength={200}
            autoFocus
          />
        )}
      </Field>
      <Field label="Company">
        {(p) => (
          <input
            {...p}
            value={draft.company}
            onChange={(e) => setDraft({ ...draft, company: e.target.value })}
            maxLength={150}
          />
        )}
      </Field>
      <div className="field-grid">
        <Field label="Source">
          {(p) => (
            <input
              {...p}
              value={draft.source}
              onChange={(e) => setDraft({ ...draft, source: e.target.value })}
              maxLength={80}
            />
          )}
        </Field>
        <Field label="Link">
          {(p) => (
            <input
              {...p}
              value={draft.url}
              onChange={(e) => setDraft({ ...draft, url: e.target.value })}
              maxLength={500}
            />
          )}
        </Field>
      </div>
    </ConfirmDialog>
  )
}
