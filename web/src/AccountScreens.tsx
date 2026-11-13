import { useEffect, useState, type FormEvent } from 'react'
import { api, errorMessage, User } from './types'
import { ThemeToggle } from './theme'
import { Alert, Button, Field, Loading } from './ui'

/** Shared shell for the two token-link screens, so they look like the login. */
function TokenShell({
  title,
  tagline,
  children,
}: {
  title: string
  tagline: string
  children: React.ReactNode
}) {
  return (
    <div className="auth-wrap">
      <div className="auth-theme">
        <ThemeToggle />
      </div>
      <aside className="auth-aside" aria-hidden="true">
        <div className="auth-aside-inner">
          <span className="auth-sticker">job hunt, organised</span>
          <h2 className="auth-headline">
            Every application.
            <br />
            Every resume version.
            <br />
            <span className="auth-headline-mark">One place.</span>
          </h2>
          <ul className="auth-points">
            <li>Save a job post in one click.</li>
            <li>Tailor your resume to it, without inventing anything.</li>
            <li>Know exactly which version you sent, and when.</li>
          </ul>
        </div>
      </aside>
      <div className="auth-card">
        <div className="auth-brand">
          <span className="brand-mark" aria-hidden="true">
            T
          </span>
          <div>
            <h1 style={{ fontSize: '1.6rem' }}>{title}</h1>
            <p className="auth-tagline">{tagline}</p>
          </div>
        </div>
        {children}
      </div>
    </div>
  )
}

/** Choose a new password from a reset link. Like VerifyEmailScreen, the
 * parent must remount this when the token changes. */
export function ResetPasswordScreen({
  onDone,
  token,
}: {
  onDone: (user: User | null) => void
  token: string
}) {
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)

  const longEnough = password.length >= 8
  const matches = password === confirm
  const canSubmit = longEnough && matches && token.length > 0

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!canSubmit || busy) return
    setBusy(true)
    setError('')
    try {
      await api('/api/auth/reset-password', {
        method: 'POST',
        body: JSON.stringify({ token, password }),
      })
      setDone(true)
      // The API signs the user in with a fresh session.
      setTimeout(() => onDone(null), 1400)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  if (!token) {
    return (
      <TokenShell title="Reset link is incomplete" tagline="This link is missing its token.">
        <div className="auth-body">
          <Alert tone="error">
            That link is incomplete. Request a new reset email and use the button in it.
          </Alert>
          <Button variant="primary" block onClick={() => onDone(null)}>
            Back to sign in
          </Button>
        </div>
      </TokenShell>
    )
  }

  if (done) {
    return (
      <TokenShell title="Password updated" tagline="You are signed in with your new password.">
        <div className="auth-body">
          <Alert tone="success">Your password has been changed. Taking you to your dashboard…</Alert>
        </div>
      </TokenShell>
    )
  }

  return (
    <TokenShell title="Choose a new password" tagline="Pick something you have not used before.">
      <form className="auth-body" onSubmit={submit} noValidate>
        <Field
          label="New password"
          hint={
            password.length > 0 && !longEnough
              ? `${8 - password.length} more character${8 - password.length === 1 ? '' : 's'} needed.`
              : 'At least 8 characters.'
          }
        >
          {(p) => (
            <input
              {...p}
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoFocus
              required
            />
          )}
        </Field>
        <Field
          label="Confirm password"
          error={confirm.length > 0 && !matches ? 'Those passwords do not match.' : undefined}
        >
          {(p) => (
            <input
              {...p}
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
            />
          )}
        </Field>

        {error && <Alert tone="error">{error}</Alert>}

        <Button type="submit" variant="primary" block loading={busy} disabled={!canSubmit}>
          {busy ? 'Updating…' : 'Update password'}
        </Button>
        <button type="button" className="link-btn auth-forgot" onClick={() => onDone(null)}>
          Back to sign in
        </button>
      </form>
    </TokenShell>
  )
}

/** Confirms an email address from a verification link.
 *
 * The token is read once into state, so the parent must remount this
 * component when the token changes (it passes a `key`). Without that, going
 * from a valid link to a spent one keeps the previous success state and the
 * page lies about the result.
 */
export function VerifyEmailScreen({ onDone, token }: { onDone: () => void; token: string }) {
  const [state, setState] = useState<'working' | 'ok' | 'error'>('working')
  const [message, setMessage] = useState('')

  useEffect(() => {
    let cancelled = false
    setState('working')
    setMessage('')
    if (!token) {
      setState('error')
      setMessage('That link is incomplete. Use the button in the verification email.')
      return
    }
    // Note on the double call: React StrictMode invokes effects twice in
    // development, so the second request finds a spent token and 400s. That
    // is ignored because the first response already set the state, and
    // production runs the effect once. Do NOT cache the outcome here: a
    // cached "ok" would make a genuine replay of the link look successful.
    api<{ email: string }>('/api/auth/verify-email', {
      method: 'POST',
      body: JSON.stringify({ token }),
    })
      .then(() => {
        if (!cancelled) setState('ok')
      })
      .catch((e) => {
        if (cancelled) return
        // If the first (StrictMode) call already succeeded, keep success.
        setState((prev) => {
          if (prev === 'ok') return prev
          setMessage(errorMessage(e))
          return 'error'
        })
      })
    return () => {
      cancelled = true
    }
  }, [token])

  if (state === 'working') {
    return <Loading label="Verifying your email…" />
  }

  return (
    <TokenShell
      title={state === 'ok' ? 'Email verified' : 'Could not verify'}
      tagline={
        state === 'ok'
          ? 'Your account is fully set up.'
          : 'The link may have expired or already been used.'
      }
    >
      <div className="auth-body">
        {state === 'ok' ? (
          <Alert tone="success">Thanks — your email address is confirmed.</Alert>
        ) : (
          <Alert tone="error">{message}</Alert>
        )}
        <Button variant="primary" block onClick={onDone}>
          {state === 'ok' ? 'Go to TrackAJob' : 'Back to sign in'}
        </Button>
      </div>
    </TokenShell>
  )
}
