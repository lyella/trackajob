import { useEffect, useState } from 'react'

type User = { id: number; email: string }
type ResumeOut = { id: number; name: string; latest_version: number }

async function api(path: string, init?: RequestInit) {
  const r = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? r.status)
  return r.json()
}

export default function App() {
  const [user, setUser] = useState<User | null>(null)
  const [resumes, setResumes] = useState<ResumeOut[]>([])
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [message, setMessage] = useState('')

  useEffect(() => {
    api('/api/auth/me')
      .then((u) => {
        setUser(u)
        return api('/api/resumes')
      })
      .then(setResumes)
      .catch(() => setUser(null))
  }, [])

  async function submit(mode: 'login' | 'signup') {
    try {
      const u = await api(`/api/auth/${mode}`, {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      })
      setUser(u)
      setMessage('')
      setResumes(await api('/api/resumes'))
    } catch (e) {
      setMessage(String(e))
    }
  }

  async function logout() {
    await api('/api/auth/logout', { method: 'POST' }).catch(() => {})
    setUser(null)
    setResumes([])
  }

  if (user) {
    return (
      <main>
        <h1>TrackAJob</h1>
        <p>
          Signed in as {user.email}.{' '}
          <button onClick={logout}>Log out</button>
        </p>
        {resumes.length === 0 ? (
          <p>
            No resumes yet. The builder arrives in milestone M3; the API for
            creating them is live.
          </p>
        ) : (
          <ul>
            {resumes.map((r) => (
              <li key={r.id}>
                {r.name} (version {r.latest_version})
              </li>
            ))}
          </ul>
        )}
      </main>
    )
  }

  return (
    <main>
      <h1>TrackAJob</h1>
      <p>Track your applications. Tailor your resume to every job post.</p>
      <form onSubmit={(e) => e.preventDefault()}>
        <input
          type="email"
          placeholder="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />{' '}
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
