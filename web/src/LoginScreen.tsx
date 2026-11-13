import { useState, type FormEvent } from 'react'
import { api, errorMessage, User } from './types'
import { Captcha, resetCaptcha, useCaptchaConfig } from './captcha'
import { ThemeToggle, useTheme } from './theme'
import { Alert, Button, Field } from './ui'

type Mode = 'login' | 'signup' | 'forgot'

/** Friendly copy for the auth failures the API can return. */
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

export function LoginScreen({
  onSignedIn,
  onContinue,
}: {
  onSignedIn: (user: User) => void
  /** Re-reads the session. Used after a signup where the account was created
   * and signed in server side, but the UI stayed here to show the
   * verification link. */
  onContinue: () => void
}) {
  const [mode, setMode] = useState<Mode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [captchaToken, setCaptchaToken] = useState<string | null>(null)
  // Set when no mail provider is configured and the API hands the link back,
  // so the user is not stuck waiting for an email that will never arrive.
  const [devLink, setDevLink] = useState<string | null>(null)

  const captchaConfig = useCaptchaConfig()
  const { theme } = useTheme()

  const emailLooksValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())
  const passwordLongEnough = password.length >= 8
  const captchaReady = !captchaConfig?.enabled || Boolean(captchaToken)

  function switchMode(next: Mode) {
    setMode(next)
    setError('')
    setNotice('')
    setDevLink(null)
    setPassword('')
    resetCaptcha(setCaptchaToken)
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    setNotice('')
    setDevLink(null)
    try {
      if (mode === 'forgot') {
        await api('/api/auth/forgot-password', {
          method: 'POST',
          body: JSON.stringify({ email: email.trim(), captcha_token: captchaToken }),
        })
        // Deliberately the same message whether or not the account exists.
        setNotice(
          'If that email has an account, a reset link is on its way. Check your inbox and spam folder.'
        )
        resetCaptcha(setCaptchaToken)
        return
      }

      const user = await api<User & { verification_link?: string }>(`/api/auth/${mode}`, {
        method: 'POST',
        body: JSON.stringify({
          email: email.trim(),
          password,
          captcha_token: captchaToken,
        }),
      })
      if (user.verification_link) {
        // No mail provider is configured: show the link instead of sending
        // the user to an inbox that will never receive anything.
        setDevLink(user.verification_link)
        setNotice('Account created. Confirm your email using the link below.')
        return
      }
      onSignedIn(user)
    } catch (err) {
      setError(humanizeAuthError(errorMessage(err)))
      resetCaptcha(setCaptchaToken)
    } finally {
      setBusy(false)
    }
  }

  const isSignup = mode === 'signup'
  const isForgot = mode === 'forgot'

  const canSubmit = isForgot
    ? emailLooksValid && captchaReady
    : isSignup
      ? emailLooksValid && passwordLongEnough && captchaReady
      : emailLooksValid && password.length > 0 && captchaReady

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
            <h1 style={{ fontSize: '1.6rem' }}>
              {isForgot ? 'Reset your password' : 'TrackAJob'}
            </h1>
            <p className="auth-tagline">
              {isForgot
                ? 'Enter your email and we will send you a reset link.'
                : isSignup
                  ? 'Create an account to start tracking.'
                  : 'Welcome back. Sign in to continue.'}
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

          {!isForgot && (
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
          )}

          {captchaConfig?.enabled && captchaConfig.siteKey && (
            <Captcha siteKey={captchaConfig.siteKey} onToken={setCaptchaToken} theme={theme} />
          )}

          {error && <Alert tone="error">{error}</Alert>}
          {notice && !devLink && <Alert tone="success">{notice}</Alert>}

          {devLink && (
            <div className="dev-link">
              <p className="dev-link-title">Email delivery is not configured</p>
              <p className="dev-link-body">
                No mail provider is set up, so this link is shown here instead of being
                emailed. Open it to confirm your address.
              </p>
              <a className="btn btn-primary btn-block" href={devLink}>
                Confirm my email
              </a>
              <button type="button" className="link-btn" onClick={onContinue}>
                Skip for now and continue
              </button>
            </div>
          )}

          <Button type="submit" variant="primary" block loading={busy} disabled={!canSubmit}>
            {busy
              ? isForgot
                ? 'Sending…'
                : isSignup
                  ? 'Creating account…'
                  : 'Signing in…'
              : isForgot
                ? 'Send reset link'
                : isSignup
                  ? 'Create account'
                  : 'Sign in'}
          </Button>

          {!isForgot && mode === 'login' && (
            <button type="button" className="link-btn auth-forgot" onClick={() => switchMode('forgot')}>
              Forgot your password?
            </button>
          )}
        </form>

        <p className="auth-footer">
          {isForgot ? (
            <button type="button" className="link-btn" onClick={() => switchMode('login')}>
              Back to sign in
            </button>
          ) : (
            <>
              {isSignup ? 'Already have an account? ' : 'New to TrackAJob? '}
              <button
                type="button"
                className="link-btn"
                onClick={() => switchMode(isSignup ? 'login' : 'signup')}
              >
                {isSignup ? 'Sign in' : 'Create an account'}
              </button>
            </>
          )}
        </p>
      </div>
    </div>
  )
}
