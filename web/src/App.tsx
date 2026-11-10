import { useEffect, useState } from 'react'
import { api, ResumeOut, User } from './types'
import { createStarterResume, ResumeEditor } from './ResumeEditor'
import { JobsPanel } from './JobsPanel'

function humanizeError(e: unknown): string {
  const raw = e instanceof Error ? e.message : String(e)
  const detail = raw.replace(/^Error:\s*/, '')
  if (detail.includes('at least 8 characters'))
    return 'Password must be at least 8 characters.'
  if (detail.includes('valid email address') || detail.includes('value is not a valid email'))
    return 'That email address does not look right.'
  if (detail.includes('already registered'))
    return 'That email is already registered. Try logging in.'
  if (detail.includes('invalid email or password'))
    return 'Email or password is incorrect.'
  return detail
}

export default function App() {
  const [user, setUser] = useState<User | null>(null)
  const [authChecked, setAuthChecked] = useState(false)
  const [resumes, setResumes] = useState<ResumeOut[]>([])
  const [editing, setEditing] = useState<ResumeOut | null>(null)
  const [tab, setTab] = useState<'resumes' | 'jobs'>('resumes')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api<User>('/api/auth/me')
      .then((u) => {
        setUser(u)
        return api<ResumeOut[]>('/api/resumes')
      })
      .then(setResumes)
      .catch(() => setUser(null))
      .finally(() => setAuthChecked(true))
  }, [])

  async function refresh() {
    setResumes(await api<ResumeOut[]>('/api/resumes'))
  }

  async function submit(mode: 'login' | 'signup') {
    setBusy(true)
    setError('')
    try {
      setUser(
        await api<User>(`/api/auth/${mode}`, {
          method: 'POST',
          body: JSON.stringify({ email, password }),
        })
      )
      await refresh()
      setNotice('')
    } catch (e) {
      setError(humanizeError(e))
    } finally {
      setBusy(false)
    }
  }

  async function logout() {
    await api('/api/auth/logout', { method: 'POST' }).catch(() => {})
    setUser(null)
    setEditing(null)
  }

  if (!authChecked) {
    return (
      <main>
        <p className="muted">Loading…</p>
      </main>
    )
  }

  if (!user) {
    const canLogin = email.trim().length > 3 && password.length > 0
    const canSignup = canLogin && password.length >= 8
    return (
      <main>
        <h1>TrackAJob</h1>
        <p className="muted">Track your applications. Tailor your resume to every job post.</p>
        <form onSubmit={(e) => e.preventDefault()} noValidate>
          <label>
            Email
            <input
              type="email"
              autoFocus
              autoComplete="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          <label>
            Password
            <input
              type="password"
              autoComplete="current-password"
              placeholder="at least 8 characters"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            {password.length > 0 && password.length < 8 && (
              <small className="hint">
                For sign up, use at least 8 characters ({8 - password.length} to go).
              </small>
            )}
          </label>
          <div className="actions">
            <button
              type="submit"
              disabled={busy || !canLogin}
              onClick={() => submit('login')}
            >
              {busy ? 'Checking…' : 'Log in'}
            </button>
            <button
              type="button"
              className="primary"
              disabled={busy || !canSignup}
              onClick={() => submit('signup')}
            >
              {busy ? 'Checking…' : 'Sign up'}
            </button>
          </div>
        </form>
        {error && <p className="form-error" role="alert">{error}</p>}
      </main>
    )
  }

  if (editing) {
    return (
      <ResumeEditor
        resume={editing}
        onClose={() => {
          setEditing(null)
          refresh()
        }}
      />
    )
  }

  return (
    <main>
      <h1>TrackAJob</h1>
      <p className="muted">
        Signed in as {user.email}. <button className="link" onClick={logout}>Log out</button>
      </p>
      {notice && <p className="notice">{notice}</p>}

      <nav className="tabs">
        <button className={tab === 'resumes' ? 'primary tab' : 'tab'} onClick={() => setTab('resumes')}>
          Resumes
        </button>
        <button className={tab === 'jobs' ? 'primary tab' : 'tab'} onClick={() => setTab('jobs')}>
          Applications
        </button>
      </nav>

      {tab === 'jobs' ? (
        <JobsPanel />
      ) : (
        <>
          <h2>Resumes</h2>
          {resumes.length === 0 && <p className="muted">No resumes yet. Create your first one.</p>}
          <ul className="resume-list">
            {resumes.map((r) => (
              <li key={r.id}>
                <a
                  href="#"
                  onClick={(e) => {
                    e.preventDefault()
                    setEditing(r)
                  }}
                >
                  {r.name}
                </a>{' '}
                <small className="muted">(version {r.latest_version})</small>
              </li>
            ))}
          </ul>
          <button
            className="primary"
            disabled={busy}
            onClick={async () => {
              setBusy(true)
              setError('')
              try {
                const r = await createStarterResume(`Resume ${resumes.length + 1}`)
                setEditing(r)
              } catch (e) {
                setError(humanizeError(e))
              } finally {
                setBusy(false)
              }
            }}
          >
            {busy ? 'Creating…' : 'New resume'}
          </button>
          {error && <p className="form-error" role="alert">{error}</p>}
        </>
      )}
    </main>
  )
}
