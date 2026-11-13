import { useCallback, useEffect, useRef, useState } from 'react'
import {
  api,
  errorMessage,
  parseResume,
  ResumeContent,
  ResumeDetail,
  ResumeVersionMeta,
} from './types'
import { formatDateTime, relativeTime } from './format'
import { ATS_GUARANTEES, scoreOf, useResumeAudit } from './ats'
import { ResumePreview } from './ResumePreview'
import { Alert, Button, ConfirmDialog, Field, Loading, useToast } from './ui'

type SaveState = 'clean' | 'dirty' | 'saving' | 'saved' | 'error'

const SAVE_LABEL: Record<SaveState, string> = {
  clean: 'All changes saved',
  dirty: 'Unsaved changes',
  saving: 'Saving…',
  saved: 'Saved',
  error: 'Could not save',
}

/** Splits a textarea into bullets, dropping blank lines so a trailing
 * newline does not create an empty bullet in the preview or the export. */
function toBullets(text: string): string[] {
  return text.split('\n').map((s) => s.trimEnd())
}

function bulletsToText(bullets: string[]): string {
  return bullets.join('\n')
}

/** The ATS panel: a live readiness score plus the specific things to fix.
 * It sits above the preview because the preview is what the user is
 * checking against it. */
function AtsPanel({ content }: { content: ResumeContent }) {
  const checks = useResumeAudit(content)
  const { score, label } = scoreOf(checks)
  const [open, setOpen] = useState(true)
  const errors = checks.filter((c) => c.level === 'error')
  const warns = checks.filter((c) => c.level === 'warn')
  const tips = checks.filter((c) => c.level === 'tip')
  const shown = [...errors, ...warns, ...tips]

  return (
    <section className="ats-panel" aria-labelledby="ats-heading">
      <div className="ats-head">
        <div>
          <h2 id="ats-heading">ATS check</h2>
          <span className="ats-summary">
            {errors.length + warns.length === 0
              ? 'No issues found'
              : `${errors.length + warns.length} to fix`}
          </span>
        </div>
        <div className="ats-score" data-level={score >= 90 ? 'good' : score >= 70 ? 'ok' : 'bad'}>
          <span className="ats-score-value tabular">{score}</span>
          <span className="ats-score-label">{label}</span>
        </div>
      </div>

      <div className="ats-bar" aria-hidden="true">
        <span
          className="ats-bar-fill"
          data-level={score >= 90 ? 'good' : score >= 70 ? 'ok' : 'bad'}
          style={{ width: `${score}%` }}
        />
      </div>

      {shown.length > 0 && (
        <>
          <button
            type="button"
            className="ats-toggle"
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
          >
            {open ? 'Hide details' : `Show ${shown.length} check${shown.length === 1 ? '' : 's'}`}
          </button>
          {open && (
            <ul className="ats-list">
              {shown.map((check) => (
                <li key={check.id} className={`ats-item ats-${check.level}`}>
                  <span className="ats-marker" aria-hidden="true">
                    {check.level === 'error' ? '!' : check.level === 'warn' ? '·' : 'i'}
                  </span>
                  <div>
                    <strong>{check.title}</strong>
                    <p>{check.detail}</p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </>
      )}

      <details className="ats-guarantees">
        <summary>What this export guarantees</summary>
        <ul>
          {ATS_GUARANTEES.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </details>
    </section>
  )
}

export function ResumeEditor({
  resumeId,
  onClose,
  onChanged,
}: {
  resumeId: number
  onClose: () => void
  onChanged: () => void
}) {
  const toast = useToast()
  const [detail, setDetail] = useState<ResumeDetail | null>(null)
  const [versions, setVersions] = useState<ResumeVersionMeta[]>([])
  const [content, setContent] = useState<ResumeContent | null>(null)
  const [loadError, setLoadError] = useState('')
  const [saveState, setSaveState] = useState<SaveState>('clean')
  const [savedAt, setSavedAt] = useState<Date | null>(null)
  const [savingVersion, setSavingVersion] = useState(false)
  const [confirmLeave, setConfirmLeave] = useState(false)
  const [revertingTo, setRevertingTo] = useState<ResumeVersionMeta | null>(null)

  const timer = useRef<number | undefined>(undefined)
  // The content we know is persisted. Compared on unload and before leaving,
  // so a debounce window cannot swallow the user's last edit.
  const persisted = useRef<string>('')
  const latest = useRef<{ content: ResumeContent | null; detail: ResumeDetail | null }>({
    content: null,
    detail: null,
  })

  latest.current = { content, detail }

  const load = useCallback(async () => {
    setLoadError('')
    try {
      const [d, vs] = await Promise.all([
        api<ResumeDetail>(`/api/resumes/${resumeId}`),
        api<ResumeVersionMeta[]>(`/api/resumes/${resumeId}/versions`),
      ])
      setDetail(d)
      setVersions(vs)
      const parsed = parseResume(d.content)
      setContent(parsed)
      persisted.current = JSON.stringify(parsed)
      setSaveState('clean')
    } catch (e) {
      setLoadError(errorMessage(e))
    }
  }, [resumeId])

  useEffect(() => {
    void load()
  }, [load])

  const saveNow = useCallback(
    async (body: ResumeContent, d: ResumeDetail) => {
      setSaveState('saving')
      try {
        await api(`/api/resumes/${d.id}/versions/${d.version}`, {
          method: 'PUT',
          body: JSON.stringify(body),
        })
        persisted.current = JSON.stringify(body)
        setSaveState('saved')
        setSavedAt(new Date())
      } catch (e) {
        setSaveState('error')
        toast(errorMessage(e), 'error')
      }
    },
    [toast]
  )

  // Debounced autosave. Typing updates the working copy; the request only
  // fires once the user pauses, and every save targets the current version.
  useEffect(() => {
    if (!content || !detail) return
    if (JSON.stringify(content) === persisted.current) return
    setSaveState('dirty')
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => {
      void saveNow(content, detail)
    }, 900)
    return () => window.clearTimeout(timer.current)
  }, [content, detail, saveNow])

  // Flush a pending edit when the tab closes or reloads.
  useEffect(() => {
    function flush() {
      const { content: c, detail: d } = latest.current
      if (!c || !d) return
      if (JSON.stringify(c) === persisted.current) return
      // sendBeacon survives unload; a fetch would be cancelled mid-flight.
      navigator.sendBeacon?.(
        `/api/resumes/${d.id}/versions/${d.version}`,
        new Blob([JSON.stringify(c)], { type: 'application/json' })
      )
    }
    window.addEventListener('pagehide', flush)
    return () => window.removeEventListener('pagehide', flush)
  }, [])

  const isDirty = content ? JSON.stringify(content) !== persisted.current : false

  useEffect(() => {
    if (!isDirty) return
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault()
      e.returnValue = ''
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [isDirty])

  if (loadError) {
    return (
      <div className="page page-narrow">
        <Alert tone="error">{loadError}</Alert>
        <div className="cluster" style={{ marginTop: '1rem' }}>
          <Button onClick={onClose}>Back to resumes</Button>
          <Button variant="primary" onClick={() => void load()}>
            Try again
          </Button>
        </div>
      </div>
    )
  }

  if (!content || !detail) return <Loading label="Loading resume…" />

  const set = (patch: Partial<ResumeContent>) => setContent({ ...content, ...patch })

  const move = <T,>(arr: T[], i: number, delta: number): T[] => {
    const j = i + delta
    if (j < 0 || j >= arr.length) return arr
    const copy = [...arr]
    ;[copy[i], copy[j]] = [copy[j], copy[i]]
    return copy
  }

  async function leave() {
    if (isDirty && detail) {
      window.clearTimeout(timer.current)
      await saveNow(content!, detail)
    }
    onClose()
  }

  async function saveNewVersion() {
    setSavingVersion(true)
    try {
      const meta = await api<ResumeVersionMeta>(`/api/resumes/${detail!.id}/versions`, {
        method: 'POST',
        body: JSON.stringify(content),
      })
      setDetail({ ...detail!, version: meta.version })
      setVersions((v) => [...v, meta])
      persisted.current = JSON.stringify(content)
      setSaveState('saved')
      setSavedAt(new Date())
      onChanged()
      toast(`Saved as version ${meta.version}.`, 'success')
    } catch (e) {
      toast(errorMessage(e), 'error')
    } finally {
      setSavingVersion(false)
    }
  }

  async function revertTo(version: ResumeVersionMeta) {
    setRevertingTo(null)
    try {
      const meta = await api<{ version: number; reverted_from: number }>(
        `/api/resumes/${detail!.id}/revert`,
        { method: 'POST', body: JSON.stringify({ version: version.version }) }
      )
      await load()
      onChanged()
      toast(`Restored version ${version.version} as version ${meta.version}.`, 'success')
    } catch (e) {
      toast(errorMessage(e), 'error')
    }
  }

  const exportHref = (fmt: 'pdf' | 'docx', version?: number) =>
    `/api/resumes/${detail.id}/export/${fmt}${version ? `?version=${version}` : ''}`

  return (
    <div className="editor">
      <header className="editor-bar">
        <Button
          onClick={() => (isDirty ? setConfirmLeave(true) : void leave())}
          aria-label="Back to resumes"
        >
          ← Back
        </Button>

        <div className="editor-title">
          <h1 title={detail.name}>{detail.name}</h1>
          <div className="cluster" style={{ gap: '0.5rem' }}>
            <span className="save-status" data-state={saveState} aria-live="polite">
              <span className="save-dot" aria-hidden="true" />
              {SAVE_LABEL[saveState]}
              {saveState === 'saved' && savedAt ? ` · ${relativeTime(savedAt.toISOString())}` : ''}
            </span>
            <span className="muted small tabular">Version {detail.version}</span>
          </div>
        </div>

        <div className="editor-bar-actions">
          <a className="btn btn-sm" href={exportHref('pdf')} download>
            Export PDF
          </a>
          <a className="btn btn-sm" href={exportHref('docx')} download>
            Export DOCX
          </a>
          <Button
            size="sm"
            variant="primary"
            onClick={saveNewVersion}
            loading={savingVersion}
            title="Snapshot the current content as a new version"
          >
            Save as new version
          </Button>
        </div>
      </header>

      <div className="editor-layout">
        <div className="editor-form">
          <section className="form-section">
            <div className="form-section-head">
              <h2>Basics</h2>
            </div>
            <div className="form-section-body">
              <Field label="Full name">
                {(p) => (
                  <input
                    {...p}
                    value={content.name}
                    onChange={(e) => set({ name: e.target.value })}
                    autoComplete="name"
                    placeholder="Your full name…"
                  />
                )}
              </Field>
              <div className="field-grid">
                <Field label="Email">
                  {(p) => (
                    <input
                      {...p}
                      type="email"
                      value={content.email ?? ''}
                      onChange={(e) => set({ email: e.target.value })}
                      autoComplete="email"
                      spellCheck={false}
                      placeholder="you@example.com…"
                    />
                  )}
                </Field>
                <Field label="Phone">
                  {(p) => (
                    <input
                      {...p}
                      type="tel"
                      value={content.phone ?? ''}
                      onChange={(e) => set({ phone: e.target.value })}
                      autoComplete="tel"
                      placeholder="+63 917 000 0000…"
                    />
                  )}
                </Field>
                <Field label="Location">
                  {(p) => (
                    <input
                      {...p}
                      value={content.location ?? ''}
                      onChange={(e) => set({ location: e.target.value })}
                      autoComplete="address-level2"
                      placeholder="City, Country…"
                    />
                  )}
                </Field>
              </div>

              <div className="stack">
                <span className="field-label">Links</span>
                {content.links.map((l, i) => (
                  <div key={i} className="row-fields">
                    <Field label="Label" hideLabel>
                      {(p) => (
                        <input
                          {...p}
                          value={l.label}
                          placeholder="GitHub…"
                          onChange={(e) => {
                            const links = [...content.links]
                            links[i] = { ...l, label: e.target.value }
                            set({ links })
                          }}
                        />
                      )}
                    </Field>
                    <Field label="URL" hideLabel>
                      {(p) => (
                        <input
                          {...p}
                          value={l.url}
                          placeholder="github.com/you…"
                          onChange={(e) => {
                            const links = [...content.links]
                            links[i] = { ...l, url: e.target.value }
                            set({ links })
                          }}
                        />
                      )}
                    </Field>
                    <Button
                      size="sm"
                      variant="ghost"
                      iconOnly
                      aria-label={`Remove link ${l.label || i + 1}`}
                      onClick={() => set({ links: content.links.filter((_, j) => j !== i) })}
                    >
                      ×
                    </Button>
                  </div>
                ))}
                <Button
                  size="sm"
                  className="btn-fit"
                  onClick={() => set({ links: [...content.links, { label: '', url: '' }] })}
                >
                  Add link
                </Button>
              </div>
            </div>
          </section>

          <section className="form-section">
            <div className="form-section-head">
              <h2>Summary</h2>
            </div>
            <div className="form-section-body">
              <Field
                label="Professional summary"
                hint="Two or three sentences. Tailoring rewrites this for each job post."
                hideLabel
              >
                {(p) => (
                  <textarea
                    {...p}
                    value={content.summary ?? ''}
                    onChange={(e) => set({ summary: e.target.value })}
                    rows={4}
                    placeholder="Backend engineer with six years building…"
                  />
                )}
              </Field>
            </div>
          </section>

          <section className="form-section">
            <div className="form-section-head">
              <h2>Skills</h2>
            </div>
            <div className="form-section-body">
              <Field
                label="Skills"
                hint="Separate with commas. Keep them to tools and methods a recruiter would search for."
                hideLabel
              >
                {(p) => (
                  <textarea
                    {...p}
                    rows={2}
                    value={content.skills.join(', ')}
                    onChange={(e) =>
                      set({
                        skills: e.target.value
                          .split(',')
                          .map((s) => s.trim())
                          .filter(Boolean),
                      })
                    }
                    placeholder="Python, PostgreSQL, React…"
                  />
                )}
              </Field>
            </div>
          </section>

          <section className="form-section">
            <div className="form-section-head">
              <h2>Experience</h2>
              <Button
                size="sm"
                onClick={() =>
                  set({
                    experience: [
                      ...content.experience,
                      { company: '', role: '', start: '', end: '', bullets: [''] },
                    ],
                  })
                }
              >
                Add role
              </Button>
            </div>
            <div className="form-section-body">
              {content.experience.length === 0 && (
                <p className="muted small">
                  No roles yet. Add the most recent job first; recruiters read top down.
                </p>
              )}
              {content.experience.map((e, i) => (
                <div key={i} className="entry-card">
                  <div className="entry-head">
                    <strong>{e.role || e.company || `Role ${i + 1}`}</strong>
                    <div className="entry-actions">
                      <Button
                        size="sm"
                        variant="ghost"
                        iconOnly
                        aria-label="Move role up"
                        disabled={i === 0}
                        onClick={() => set({ experience: move(content.experience, i, -1) })}
                      >
                        ↑
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        iconOnly
                        aria-label="Move role down"
                        disabled={i === content.experience.length - 1}
                        onClick={() => set({ experience: move(content.experience, i, 1) })}
                      >
                        ↓
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        iconOnly
                        aria-label={`Remove role ${e.role || i + 1}`}
                        onClick={() =>
                          set({ experience: content.experience.filter((_, j) => j !== i) })
                        }
                      >
                        ×
                      </Button>
                    </div>
                  </div>
                  <div className="field-grid field-grid-narrow">
                    <Field label="Company">
                      {(p) => (
                        <input
                          {...p}
                          value={e.company}
                          placeholder="Acme Inc…"
                          onChange={(ev) => {
                            const exp = [...content.experience]
                            exp[i] = { ...e, company: ev.target.value }
                            set({ experience: exp })
                          }}
                        />
                      )}
                    </Field>
                    <Field label="Role">
                      {(p) => (
                        <input
                          {...p}
                          value={e.role}
                          placeholder="Backend Engineer…"
                          onChange={(ev) => {
                            const exp = [...content.experience]
                            exp[i] = { ...e, role: ev.target.value }
                            set({ experience: exp })
                          }}
                        />
                      )}
                    </Field>
                  </div>
                  <div className="field-grid field-grid-narrow">
                    <Field label="Start">
                      {(p) => (
                        <input
                          {...p}
                          value={e.start}
                          placeholder="2022…"
                          onChange={(ev) => {
                            const exp = [...content.experience]
                            exp[i] = { ...e, start: ev.target.value }
                            set({ experience: exp })
                          }}
                        />
                      )}
                    </Field>
                    <Field label="End">
                      {(p) => (
                        <input
                          {...p}
                          value={e.end ?? ''}
                          placeholder="Blank for Present…"
                          onChange={(ev) => {
                            const exp = [...content.experience]
                            exp[i] = { ...e, end: ev.target.value }
                            set({ experience: exp })
                          }}
                        />
                      )}
                    </Field>
                  </div>
                  <Field label="Achievements" hint="One per line. Start with a verb and a number.">
                    {(p) => (
                      <textarea
                        {...p}
                        value={bulletsToText(e.bullets)}
                        rows={Math.min(Math.max(e.bullets.length + 1, 3), 8)}
                        placeholder={'Cut p95 latency from 900ms to 180ms…'}
                        onChange={(ev) => {
                          const exp = [...content.experience]
                          exp[i] = { ...e, bullets: toBullets(ev.target.value) }
                          set({ experience: exp })
                        }}
                      />
                    )}
                  </Field>
                </div>
              ))}
            </div>
          </section>

          <section className="form-section">
            <div className="form-section-head">
              <h2>Education</h2>
              <Button
                size="sm"
                onClick={() =>
                  set({ education: [...content.education, { school: '', degree: '', year: '' }] })
                }
              >
                Add education
              </Button>
            </div>
            <div className="form-section-body">
              {content.education.length === 0 && (
                <p className="muted small">No education entries yet.</p>
              )}
              {content.education.map((e, i) => (
                <div key={i} className="entry-card">
                  <div className="entry-head">
                    <strong>{e.school || `Education ${i + 1}`}</strong>
                    <div className="entry-actions">
                      <Button
                        size="sm"
                        variant="ghost"
                        iconOnly
                        aria-label="Move education up"
                        disabled={i === 0}
                        onClick={() => set({ education: move(content.education, i, -1) })}
                      >
                        ↑
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        iconOnly
                        aria-label="Move education down"
                        disabled={i === content.education.length - 1}
                        onClick={() => set({ education: move(content.education, i, 1) })}
                      >
                        ↓
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        iconOnly
                        aria-label={`Remove education ${e.school || i + 1}`}
                        onClick={() =>
                          set({ education: content.education.filter((_, j) => j !== i) })
                        }
                      >
                        ×
                      </Button>
                    </div>
                  </div>
                  <div className="field-grid">
                    <Field label="School">
                      {(p) => (
                        <input
                          {...p}
                          value={e.school}
                          placeholder="University of the Philippines…"
                          onChange={(ev) => {
                            const edu = [...content.education]
                            edu[i] = { ...e, school: ev.target.value }
                            set({ education: edu })
                          }}
                        />
                      )}
                    </Field>
                    <Field label="Degree">
                      {(p) => (
                        <input
                          {...p}
                          value={e.degree}
                          placeholder="BS Computer Science…"
                          onChange={(ev) => {
                            const edu = [...content.education]
                            edu[i] = { ...e, degree: ev.target.value }
                            set({ education: edu })
                          }}
                        />
                      )}
                    </Field>
                    <Field label="Year">
                      {(p) => (
                        <input
                          {...p}
                          value={e.year ?? ''}
                          placeholder="2019…"
                          onChange={(ev) => {
                            const edu = [...content.education]
                            edu[i] = { ...e, year: ev.target.value }
                            set({ education: edu })
                          }}
                        />
                      )}
                    </Field>
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="form-section">
            <div className="form-section-head">
              <h2>Projects</h2>
              <Button
                size="sm"
                onClick={() =>
                  set({ projects: [...content.projects, { name: '', description: '', url: '' }] })
                }
              >
                Add project
              </Button>
            </div>
            <div className="form-section-body">
              {content.projects.length === 0 && (
                <p className="muted small">No projects yet. Useful when experience is short.</p>
              )}
              {content.projects.map((p, i) => (
                <div key={i} className="entry-card">
                  <div className="entry-head">
                    <strong>{p.name || `Project ${i + 1}`}</strong>
                    <div className="entry-actions">
                      <Button
                        size="sm"
                        variant="ghost"
                        iconOnly
                        aria-label="Move project up"
                        disabled={i === 0}
                        onClick={() => set({ projects: move(content.projects, i, -1) })}
                      >
                        ↑
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        iconOnly
                        aria-label="Move project down"
                        disabled={i === content.projects.length - 1}
                        onClick={() => set({ projects: move(content.projects, i, 1) })}
                      >
                        ↓
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        iconOnly
                        aria-label={`Remove project ${p.name || i + 1}`}
                        onClick={() =>
                          set({ projects: content.projects.filter((_, j) => j !== i) })
                        }
                      >
                        ×
                      </Button>
                    </div>
                  </div>
                  <div className="field-grid">
                    <Field label="Name">
                      {(f) => (
                        <input
                          {...f}
                          value={p.name}
                          placeholder="TrackAJob…"
                          onChange={(ev) => {
                            const pr = [...content.projects]
                            pr[i] = { ...p, name: ev.target.value }
                            set({ projects: pr })
                          }}
                        />
                      )}
                    </Field>
                    <Field label="Link">
                      {(f) => (
                        <input
                          {...f}
                          value={p.url ?? ''}
                          placeholder="github.com/you/project…"
                          onChange={(ev) => {
                            const pr = [...content.projects]
                            pr[i] = { ...p, url: ev.target.value }
                            set({ projects: pr })
                          }}
                        />
                      )}
                    </Field>
                  </div>
                  <Field label="Description">
                    {(f) => (
                      <textarea
                        {...f}
                        rows={2}
                        value={p.description}
                        placeholder="What it does and what you built…"
                        onChange={(ev) => {
                          const pr = [...content.projects]
                          pr[i] = { ...p, description: ev.target.value }
                          set({ projects: pr })
                        }}
                      />
                    )}
                  </Field>
                </div>
              ))}
            </div>
          </section>

          <section className="form-section">
            <div className="form-section-head">
              <h2>Version history</h2>
              <span className="muted small tabular">
                {versions.length} version{versions.length === 1 ? '' : 's'}
              </span>
            </div>
            <div className="form-section-body">
              <ul className="version-list">
                {[...versions].reverse().map((v) => {
                  const isCurrent = v.version === detail.version
                  return (
                    <li key={v.version} className="version-row" data-current={isCurrent}>
                      <span className="version-tag">v{v.version}</span>
                      <span className="version-when" title={formatDateTime(v.created_at)}>
                        {formatDateTime(v.created_at)}
                        {isCurrent ? ' · current' : ''}
                      </span>
                      <span className="version-actions">
                        <a
                          className="btn btn-ghost btn-sm"
                          href={exportHref('pdf', v.version)}
                          download
                          aria-label={`Download version ${v.version} as PDF`}
                          title="Download this version as PDF"
                        >
                          PDF
                        </a>
                        <a
                          className="btn btn-ghost btn-sm"
                          href={exportHref('docx', v.version)}
                          download
                          aria-label={`Download version ${v.version} as DOCX`}
                          title="Download this version as DOCX"
                        >
                          DOCX
                        </a>
                        {!isCurrent && (
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => setRevertingTo(v)}
                            title={`Restore version ${v.version}`}
                          >
                            Restore
                          </Button>
                        )}
                      </span>
                    </li>
                  )
                })}
              </ul>
              <p className="field-hint">
                Editing updates the current version in place. “Save as new version” snapshots
                it, and every tailored copy gets its own version.
              </p>
            </div>
          </section>
        </div>

        <div className="preview-column">
          <AtsPanel content={content} />
          <div className="preview-toolbar">
            <h2>Live preview</h2>
            <span className="muted small">Matches the PDF export</span>
          </div>
          <ResumePreview content={content} />
        </div>
      </div>

      <ConfirmDialog
        open={confirmLeave}
        title="Save your changes first?"
        confirmLabel="Save and go back"
        cancelLabel="Keep editing"
        tone="primary"
        onCancel={() => setConfirmLeave(false)}
        onConfirm={async () => {
          setConfirmLeave(false)
          await leave()
        }}
      >
        <p>You have edits that have not been saved yet.</p>
      </ConfirmDialog>

      <ConfirmDialog
        open={revertingTo !== null}
        title={`Restore version ${revertingTo?.version}?`}
        confirmLabel="Restore"
        tone="primary"
        onCancel={() => setRevertingTo(null)}
        onConfirm={() => revertingTo && void revertTo(revertingTo)}
      >
        <p>
          The content of version {revertingTo?.version} is copied into a new version. Nothing in
          your history is deleted, so you can always go back again.
        </p>
      </ConfirmDialog>
    </div>
  )
}
