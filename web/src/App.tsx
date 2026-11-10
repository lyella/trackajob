import { useEffect, useState } from 'react'
import { api, ResumeOut, User } from './types'
import { createStarterResume, ResumeEditor } from './ResumeEditor'

export default function App() {
  const [user, setUser] = useState<User | null>(null)
  const [resumes, setResumes] = useState<ResumeOut[]>([])
  const [editing, setEditing] = useState<ResumeOut | null>(null)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [message, setMessage] = useState('')

  useEffect(() => {
    api<User>('/api/auth/me')
      .then((u) => {
        setUser(u)
        return api<ResumeOut[]>('/api/resumes')
      })
      .then(setResumes)
      .catch(() => setUser(null))
  }, [])

  async function refresh() {
    setResumes(await api<ResumeOut[]>('/api/resumes'))
  }

  async function submit(mode: 'login' | 'signup') {
    try {
      setUser(await api<User>(`/api/auth/${mode}`, {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      }))
      await refresh()
      setMessage('')
    } catch (e) {
      setMessage(String(e))
    }
  }

  async function logout() {
    await api('/api/auth/logout', { method: 'POST' }).catch(() => {})
    setUser(null)
  }

  if (!user) {
    return (
      <main>
        <h1>TrackAJob</h1>
        <p>Track your applications. Tailor your resume to every job post.</p>
        <form onSubmit={(e) => e.preventDefault()}>
          <input type="email" placeholder="email" value={email} onChange={(e) => setEmail(e.target.value)} />{' '}
          <input
            type="password"
            placeholder="password (8+ chars)"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </form>
        <p>
          <button onClick={() => submit('login')}>Log in</button>{' '}
          <button onClick={() => submit('signup')}>Sign up</button>
        </p>
        {message && <p style={{ color: '#a33' }}>{message}</p>}
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
      <p>
        Signed in as {user.email}. <button onClick={logout}>Log out</button>
      </p>
      <h2>Resumes</h2>
      {resumes.length === 0 && <p>No resumes yet.</p>}
      <ul>
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
            (version {r.latest_version})
          </li>
        ))}
      </ul>
      <button
        onClick={async () => {
          const r = await createStarterResume(`Resume ${resumes.length + 1}`)
          setEditing(r)
        }}
      >
        New resume
      </button>
    </main>
  )
}
