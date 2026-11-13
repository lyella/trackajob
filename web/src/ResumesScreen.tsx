import { useState } from 'react'
import { api, emptyResume, errorMessage, ResumeOut } from './types'
import { relativeTime } from './format'
import { Button, ConfirmDialog, EmptyState, Field, Loading, useToast } from './ui'

/** Resumes list. Each resume is a card with its version count and a direct
 * route into the editor, plus rename and delete so the list is not a
 * write-only pile. */
export function ResumesScreen({
  resumes,
  onOpen,
  onChanged,
}: {
  resumes: ResumeOut[] | null
  onOpen: (id: number) => void
  onChanged: () => Promise<void> | void
}) {
  const toast = useToast()
  const [creating, setCreating] = useState(false)
  const [renaming, setRenaming] = useState<ResumeOut | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const [deleting, setDeleting] = useState<ResumeOut | null>(null)
  const [busy, setBusy] = useState(false)

  async function create() {
    setCreating(true)
    try {
      const r = await api<ResumeOut>('/api/resumes', {
        method: 'POST',
        body: JSON.stringify({
          name: `Resume ${(resumes?.length ?? 0) + 1}`,
          content: emptyResume(''),
        }),
      })
      await onChanged()
      toast('Resume created. Fill in your details.', 'success')
      onOpen(r.id)
    } catch (e) {
      toast(errorMessage(e), 'error')
    } finally {
      setCreating(false)
    }
  }

  async function saveRename() {
    if (!renaming) return
    const name = renameValue.trim()
    if (!name) return
    setBusy(true)
    try {
      await api(`/api/resumes/${renaming.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ name }),
      })
      await onChanged()
      toast('Resume renamed.', 'success')
      setRenaming(null)
    } catch (e) {
      toast(errorMessage(e), 'error')
    } finally {
      setBusy(false)
    }
  }

  async function confirmDelete() {
    if (!deleting) return
    setBusy(true)
    try {
      await api(`/api/resumes/${deleting.id}`, { method: 'DELETE' })
      await onChanged()
      toast(`Deleted “${deleting.name}”.`, 'success')
      setDeleting(null)
    } catch (e) {
      toast(errorMessage(e), 'error')
    } finally {
      setBusy(false)
    }
  }

  const totalVersions =
    resumes?.reduce((sum, r) => sum + Math.max(r.latest_version, 0), 0) ?? 0

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <span className="eyebrow">Library</span>
          <h1>Resumes</h1>
          <p>Your base resume and every tailored version, in one place.</p>
        </div>
        <Button variant="primary" onClick={create} loading={creating}>
          {creating ? 'Creating…' : 'New resume'}
        </Button>
      </div>

      {resumes === null ? (
        <Loading label="Loading resumes…" />
      ) : resumes.length === 0 ? (
        <EmptyState
          glyph="📄"
          title="No resumes yet"
          action={
            <Button variant="primary" onClick={create} loading={creating}>
              Create your first resume
            </Button>
          }
        >
          Start with one base resume. You can tailor a copy of it against any job
          post later, and every version is kept.
        </EmptyState>
      ) : (
        <>
          <div className="stat-row">
            <div className="stat">
              <div className="stat-value">{resumes.length}</div>
              <div className="stat-label">Resume{resumes.length === 1 ? '' : 's'}</div>
            </div>
            <div className="stat">
              <div className="stat-value">{totalVersions}</div>
              <div className="stat-label">Version{totalVersions === 1 ? '' : 's'}</div>
            </div>
          </div>

          <ul className="card-list" style={{ listStyle: 'none', padding: 0, margin: 0 }}>
            {resumes.map((r) => (
              <li key={r.id} className="resume-card">
                <div className="resume-card-main">
                  <a
                    className="resume-card-title"
                    href={`#/resumes/${r.id}`}
                    onClick={(e) => {
                      e.preventDefault()
                      onOpen(r.id)
                    }}
                    title={r.name}
                  >
                    {r.name}
                  </a>
                  <div className="resume-card-meta">
                    <span className="tabular">
                      {r.latest_version} version{r.latest_version === 1 ? '' : 's'}
                    </span>
                    {r.versions && r.versions.length > 0 && (
                      <>
                        <span aria-hidden="true">·</span>
                        <span>
                          Updated{' '}
                          <time dateTime={r.versions[r.versions.length - 1].created_at}>
                            {relativeTime(r.versions[r.versions.length - 1].created_at)}
                          </time>
                        </span>
                      </>
                    )}
                  </div>
                </div>
                <div className="resume-card-actions">
                  <Button size="sm" variant="primary" onClick={() => onOpen(r.id)}>
                    Edit
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => {
                      setRenaming(r)
                      setRenameValue(r.name)
                    }}
                  >
                    Rename
                  </Button>
                  <Button size="sm" variant="danger" onClick={() => setDeleting(r)}>
                    Delete
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}

      <ConfirmDialog
        open={renaming !== null}
        title="Rename resume"
        confirmLabel="Save name"
        tone="primary"
        busy={busy}
        onCancel={() => setRenaming(null)}
        onConfirm={saveRename}
      >
        <Field label="Resume name">
          {(p) => (
            <input
              {...p}
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') void saveRename()
              }}
              maxLength={120}
              autoFocus
            />
          )}
        </Field>
        <p className="small muted">
          Renaming does not create a new version, so your version history stays clean.
        </p>
      </ConfirmDialog>

      <ConfirmDialog
        open={deleting !== null}
        title="Delete this resume?"
        confirmLabel="Delete resume"
        busy={busy}
        onCancel={() => setDeleting(null)}
        onConfirm={confirmDelete}
      >
        <p>
          <strong>{deleting?.name}</strong> and all {deleting?.latest_version ?? 0} of its
          versions will be permanently deleted.
        </p>
        <p className="small muted">
          Applications that were sent with one of these versions keep their record, but the
          link to the resume version is removed. This cannot be undone.
        </p>
      </ConfirmDialog>
    </div>
  )
}
