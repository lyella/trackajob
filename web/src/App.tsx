import { useEffect, useState } from 'react'

type Health = { status: string; database: string }

export default function App() {
  const [backend, setBackend] = useState<string>('checking...')

  useEffect(() => {
    fetch('/api/health')
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((h: Health) => setBackend(`${h.status}, db ${h.database}`))
      .catch(() => setBackend('unreachable'))
  }, [])

  return (
    <main>
      <h1>TrackAJob</h1>
      <p>
        Track your applications. Tailor your resume to every job post. v1 is
        being built.
      </p>
      <p>Backend: {backend}</p>
    </main>
  )
}
