import { useState, type FormEvent } from 'react'
import { api, errorMessage, User } from './types'
import { ThemeToggle } from './theme'
import { Alert, Button, Field } from './ui'

type Mode = 'login' | 'signup'

/** Friendly copy for the handful of auth failures the API can return. */
function humanizeAuthError(message: string): string {
  const m = message.toLowerCase()
  if (m.includes('at least 8 characters'))
    return 'Use at least 8 characters for your password.'
  if (m.includes('valid email'))
    return 'That email address does not look right. Check it and try again.'
  if (m.includes('already registered'))
    return 'That email already has an account. Try signing in instead.'
  if (m.includes('invalid email or password'))
    return 'Email or password is incorrect. Check both and try again.'
  return message
}

export function LoginScreen({ onSignedIn }: { onSignedIn: (user: User) => void }) {
  const [mode, setMode] = useState<Mode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const emailLooksValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())
  const passwordLongEnough = password.length >= 8

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    try {
      const user = await api<User>(`/api/auth/${mode}`, {
        method: 'POST',
        body: JSON.stringify({ email: email.trim(), password }),
      })
      onSignedIn(user)
    } catch (err) {
      setError(humanizeAuthError(errorMessage(err)))
    } finally {
      setBusy(false)
    }
  }

  const isSignup = mode === 'signup'

  return (
    <div className="auth-wrap">
      <div className="auth-theme">
        <ThemeToggle />
      </div>
      {/* Left panel: the pitch. Hidden on narrow screens, where the form is
          the only thing that matters. */}
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
          <div className="auth-marquee">
            <span>ATS-SAFE PDF + DOCX</span>
            <span aria-hidden="true">✦</span>
            <span>VERSION HISTORY</span>
            <span aria-hidden="true">✦</span>
            <span>DIFF BEFORE YOU SEND</span>
          </div>
        </div>
      </aside>

      <div className="auth-card">
        <div className="auth-brand">
          <span className="brand-mark" aria-hidden="true">
            T
          </span>
          <div>
            <h1 style={{ fontSize: '1.6rem' }}>TrackAJob</h1>
            <p className="auth-tagline">
              {isSignup ? 'Create an account to start tracking.' : 'Welcome back. Sign in to continue.'}
            </p>
          </div>
        </div>

        <form className="auth-body" onSubmit={submit} noValidate>
          <Field label="Email">
            {(p) => (
              <input
                {...p}
                type="email"
                name="email"
                autoComplete="email"
                spellCheck={false}
                autoCapitalize="none"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoFocus
                required
              />
            )}
          </Field>

          <Field
            label="Password"
            hint={
              isSignup
                ? password.length > 0 && !passwordLongEnough
                  ? `${8 - password.length} more character${8 - password.length === 1 ? '' : 's'} needed.`
                  : 'At least 8 characters.'
                : undefined
            }
          >
            {(p) => (
              <input
                {...p}
                type="password"
                name="password"
                autoComplete={isSignup ? 'new-password' : 'current-password'}
                placeholder={isSignup ? 'Choose a password…' : 'Your password…'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            )}
          </Field>

          {error && <Alert tone="error">{error}</Alert>}

          <Button
            type="submit"
            variant="primary"
            block
            loading={busy}
            disabled={!emailLooksValid || password.length === 0 || (isSignup && !passwordLongEnough)}
          >
            {busy
              ? isSignup
                ? 'Creating account…'
                : 'Signing in…'
              : isSignup
                ? 'Create account'
                : 'Sign in'}
          </Button>
        </form>

        <p className="auth-footer">
          {isSignup ? 'Already have an account? ' : 'New to TrackAJob? '}
          <button
            type="button"
            className="link-btn"
            onClick={() => {
              setMode(isSignup ? 'login' : 'signup')
              setError('')
            }}
          >
            {isSignup ? 'Sign in' : 'Create an account'}
          </button>
        </p>
      </div>
    </div>
  )
}
