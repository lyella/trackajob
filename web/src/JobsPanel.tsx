import { useEffect, useState } from 'react'
import { api, ResumeContent, ResumeOut } from './types'
import { DiffView } from './DiffView'

export const STATUSES = ['interested', 'applied', 'interview', 'offer', 'rejected', 'closed'] as const
export type JobStatus = (typeof STATUSES)[number]

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

const emptyForm = { title: '', company: '', source: '', url: '', description: '', notes: '' }

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

export function JobsPanel() {
  const [jobs, setJobs] = useState<Job[] | null>(null)
  const [filter, setFilter] = useState<JobStatus | 'all'>('all')
  const [form, setForm] = useState(emptyForm)
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState('')
  const [resumes, setResumes] = useState<ResumeOut[]>([])
  const [tailorJobId, setTailorJobId] = useState<number | null>(null)
  const [tailorResumeId, setTailorResumeId] = useState<number | null>(null)
  const [prompt, setPrompt] = useState('')
  const [tailoring, setTailoring] = useState(false)
  const [tailorResult, setTailorResult] = useState<TailorResponse | null>(null)

  useEffect(() => {
    api<Job[]>('/api/jobs')
      .then(setJobs)
      .catch((e) => setError(String(e)))
    api<ResumeOut[]>('/api/resumes')
      .then((rs) => {
        setResumes(rs)
        if (rs.length > 0) setTailorResumeId(rs[0].id)
      })
      .catch(() => {})
  }, [])

  async function runTailor(jobId: number) {
    if (tailorResumeId == null) return
    setTailoring(true)
    setError('')
    setTailorResult(null)
    try {
      const r = await api<TailorResponse>(`/api/resumes/${tailorResumeId}/tailor`, {
        method: 'POST',
        body: JSON.stringify({ job_id: jobId, prompt }),
      })
      setTailorResult(r)
    } catch (e) {
      setError(String(e))
    } finally {
      setTailoring(false)
    }
  }

  async function markAppliedWith(job: Job, versionId: number, version: number) {
    const updated = await api<Job>(`/api/jobs/${job.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ status: 'applied', resume_version_id: versionId }),
    })
    setJobs((js) => js!.map((j) => (j.id === job.id ? updated : j)))
    setTailorJobId(null)
    setTailorResult(null)
    void version
  }

  async function addJob() {
    if (!form.title.trim()) {
      setError('A role title is required.')
      return
    }
    setAdding(true)
    setError('')
    try {
      await api<Job>('/api/jobs', { method: 'POST', body: JSON.stringify(form) })
      setForm(emptyForm)
      setJobs(await api<Job[]>('/api/jobs'))
    } catch (e) {
      setError(String(e))
    } finally {
      setAdding(false)
    }
  }

  async function patch(id: number, data: Partial<Job>) {
    const updated = await api<Job>(`/api/jobs/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    })
    setJobs((js) => js!.map((j) => (j.id === id ? updated : j)))
  }

  async function remove(id: number) {
    await api(`/api/jobs/${id}`, { method: 'DELETE' }).catch(() => {})
    setJobs((js) => js!.filter((j) => j.id !== id))
  }

  const shown = jobs?.filter((j) => filter === 'all' || j.status === filter) ?? []

  return (
    <div>
      <h2>Applications</h2>

      <details className="add-job" open={jobs?.length === 0}>
        <summary>Add a job post</summary>
        <div className="add-form">
          <label>
            Role title
            <input
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              placeholder="Backend Developer"
            />
          </label>
          <label>
            Company
            <input
              value={form.company}
              onChange={(e) => setForm({ ...form, company: e.target.value })}
              placeholder="Acme Inc"
            />
          </label>
          <label>
            Source
            <input
              value={form.source}
              onChange={(e) => setForm({ ...form, source: e.target.value })}
              placeholder="LinkedIn, Indeed, referral..."
            />
          </label>
          <label>
            Link
            <input
              value={form.url}
              onChange={(e) => setForm({ ...form, url: e.target.value })}
              placeholder="https://..."
            />
          </label>
          <label>
            Job description (paste)
            <textarea
              rows={5}
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder="Paste the full job post here..."
            />
          </label>
          <button className="primary" onClick={addJob} disabled={adding}>
            {adding ? 'Saving…' : 'Save job'}
          </button>
        </div>
      </details>

      {error && <p className="form-error" role="alert">{error}</p>}

      <div className="filters">
        <button className={filter === 'all' ? 'primary' : ''} onClick={() => setFilter('all')}>
          all ({jobs?.length ?? 0})
        </button>
        {STATUSES.map((s) => {
          const n = jobs?.filter((j) => j.status === s).length ?? 0
          return (
            <button key={s} className={filter === s ? 'primary' : ''} onClick={() => setFilter(s)}>
              {s} ({n})
            </button>
          )
        })}
      </div>

      {jobs === null && <p className="muted">Loading…</p>}
      {jobs !== null && shown.length === 0 && (
        <p className="muted">No jobs under this filter yet.</p>
      )}

      {shown.map((j) => (
        <div key={j.id} className={`job-card status-${j.status}`}>
          <div className="job-head">
            <strong>{j.title}</strong>
            {j.company && <span> at {j.company}</span>}
            {j.source && <small className="muted"> via {j.source}</small>}
            <select
              value={j.status}
              onChange={(e) => patch(j.id, { status: e.target.value as JobStatus })}
            >
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            <button className="link" onClick={() => remove(j.id)}>
              delete
            </button>
            <button className="link" onClick={() => { setTailorResult(null); setTailorJobId(tailorJobId === j.id ? null : j.id) }}>
              tailor
            </button>
          </div>
          {j.sent_resume && <p className="sent-resume">sent with: {j.sent_resume}</p>}
          {tailorJobId === j.id && (
            <div className="tailor-panel">
              <select
                value={tailorResumeId ?? ''}
                onChange={(e) => setTailorResumeId(Number(e.target.value))}
              >
                {resumes.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                  </option>
                ))}
              </select>{' '}
              <input
                placeholder="optional instruction, e.g. emphasize backend work"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
              />{' '}
              <button className="primary" disabled={tailoring || !tailorResumeId} onClick={() => runTailor(j.id)}>
                {tailoring ? 'Tailoring�' : 'Tailor resume'}
              </button>
              {tailorResult && (
                <div className="tailor-result">
                  <p className="muted">
                    v{tailorResult.base_version} → v{tailorResult.version}, {tailorResult.tokens_in}/{tailorResult.tokens_out} tokens, ${tailorResult.cost_usd.toFixed(4)}
                  </p>
                  {tailorResult.notes && <p className="notice">{tailorResult.notes}</p>}
                  {tailorResult.warnings.map((w, i) => (
                    <p key={i} className="form-error">{w}</p>
                  ))}
                  <DiffView before={tailorResult.base_content} after={tailorResult.content} />
                  <div className="actions">
                    <a className="export-btn" href={`/api/resumes/${tailorResult.resume_id}/export/pdf`}>
                      Export PDF
                    </a>{' '}
                    <a className="export-btn" href={`/api/resumes/${tailorResult.resume_id}/export/docx`}>
                      Export DOCX
                    </a>{' '}
                    <button
                      onClick={() => markAppliedWith(j, tailorResult.version_id, tailorResult.version)}
                    >
                      Mark applied with v{tailorResult.version}
                    </button>{' '}
                    <button
                      onClick={async () => {
                        await api(`/api/resumes/${tailorResult.resume_id}/revert`, {
                          method: 'POST',
                          body: JSON.stringify({ version: tailorResult.base_version }),
                        })
                        setTailorResult(null)
                      }}
                    >
                      Revert to v{tailorResult.base_version}
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
          {j.url && (
            <a href={j.url} target="_blank" rel="noreferrer" className="job-link">
              {j.url}
            </a>
          )}
          {j.description && (
            <details className="job-desc">
              <summary>job description</summary>
              <pre>{j.description}</pre>
            </details>
          )}
          <textarea
            className="job-notes"
            placeholder="notes"
            rows={2}
            defaultValue={j.notes}
            onBlur={(e) => {
              if (e.target.value !== j.notes) patch(j.id, { notes: e.target.value })
            }}
          />
          <div className="job-history">
            {j.status_history.map((h, i) => (
              <small key={i} className="muted">
                {h.status} @ {h.at.slice(0, 10)}{' '}
              </small>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
