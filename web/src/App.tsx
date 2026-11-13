import { useCallback, useEffect, useState } from 'react'
import { api, errorMessage, ResumeOut, User } from './types'
import { ResetPasswordScreen, VerifyEmailScreen } from './AccountScreens'
import { ResumeEditor } from './ResumeEditor'
import { ResumesScreen } from './ResumesScreen'
import { JobsPanel } from './JobsPanel'
import { LoginScreen } from './LoginScreen'
import { StatsScreen } from './StatsScreen'
import { useRoute } from './router'
import { ThemeProvider, ThemeToggle } from './theme'
import { Alert, Button, ConfirmDialog, Loading, ToastProvider, useToast } from './ui'

/** Password help for a signed-in user.
 *
 * Asking for a reset link while signed in is the enumeration-safe way to
 * offer it: the caller is already authenticated as the owner, so showing
 * their own link reveals nothing. The public forgot-password form never
 * returns a link, because that would tell a stranger whether an account
 * exists.
 */
function PasswordDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [link, setLink] = useState('')
  const [expires, setExpires] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open) {
      setLink('')
      setError('')
    }
  }, [open])

  async function requestLink() {
    setBusy(true)
    setError('')
    try {
      const r = await api<{ reset_link: string; expires_minutes: number }>(
        '/api/auth/reset-link',
        { method: 'POST', body: JSON.stringify({}) }
      )
      setLink(r.reset_link)
      setExpires(r.expires_minutes)
      if (!r.reset_link) {
        setError(
          'A reset link was created but email delivery is not configured, so it cannot be shown here.'
        )
      }
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <ConfirmDialog
      open={open}
      title="Change your password"
      confirmLabel={link ? 'Done' : 'Get a reset link'}
      cancelLabel="Close"
      tone="primary"
      busy={busy}
      onCancel={onClose}
      onConfirm={link ? onClose : requestLink}
    >
      {link ? (
        <>
          <p>Use this link to choose a new password. It works once and expires in {expires} minutes.</p>
          <a className="btn btn-primary btn-block" href={link}>
            Choose a new password
          </a>
          <p className="small muted">
            This is shown here because email delivery is not configured. Once a mail provider is
            set up, the link is emailed instead.
          </p>
        </>
      ) : (
        <p>
          We will create a one-time link you can use to set a new password. Your current password
          keeps working until you use it.
        </p>
      )}
      {error && <Alert tone="error">{error}</Alert>}
    </ConfirmDialog>
  )
}

type ImportPayload = Record<string, string>

/** Shown until the address is confirmed. The app stays fully usable, so a
 * broken mail provider cannot lock anyone out of their own data. */
function VerifyBanner({ onVerified }: { onVerified: () => void }) {
  const [state, setState] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle')
  const [message, setMessage] = useState('')

  async function resend() {
    setState('sending')
    setMessage('')
    try {
      await api('/api/auth/resend-verification', {
        method: 'POST',
        body: JSON.stringify({}),
      })
      setState('sent')
    } catch (e) {
      setState('error')
      setMessage(errorMessage(e))
    }
  }

  return (
    <div className="verify-banner" role="status">
      <div className="verify-banner-text">
        <strong>Confirm your email address.</strong>{' '}
        {state === 'sent'
          ? 'We sent a new link. Check your inbox and spam folder.'
          : 'We sent you a link when you signed up. Confirm it so you never lose access to your account.'}
        {state === 'error' && <span className="verify-banner-error"> {message}</span>}
      </div>
      <div className="cluster">
        <Button size="sm" onClick={resend} loading={state === 'sending'} disabled={state === 'sent'}>
          {state === 'sent' ? 'Link sent' : 'Resend link'}
        </Button>
        <Button size="sm" variant="ghost" onClick={onVerified} title="Check again">
          I have confirmed
        </Button>
      </div>
    </div>
  )
}

function Shell({
  user,
  onSignedOut,
  onUserChanged,
}: {
  user: User
  onSignedOut: () => void
  onUserChanged: () => void
}) {
  const { route, navigate, setApplicationQuery } = useRoute()
  const [resumes, setResumes] = useState<ResumeOut[] | null>(null)
  const [pendingImport, setPendingImport] = useState<ImportPayload | null>(null)
  const [passwordOpen, setPasswordOpen] = useState(false)
  const toast = useToast()

  const refreshResumes = useCallback(async () => {
    try {
      setResumes(await api<ResumeOut[]>('/api/resumes'))
    } catch (e) {
      toast(errorMessage(e), 'error')
      setResumes([])
    }
  }, [toast])

  useEffect(() => {
    void refreshResumes()
  }, [refreshResumes])

  // Bookmarklet handoff: a scraped page opens this app at #importing and
  // postMessages the job data once it finishes loading. The hash is the
  // click token: without it, messages are ignored entirely. The ack lets
  // the bookmarklet stop retrying as soon as the payload has landed.
  useEffect(() => {
    function receiveImport(ev: MessageEvent) {
      if (window.location.hash !== '#importing') return
      const data = ev.data as { type?: string; job?: ImportPayload } | null
      if (!data || data.type !== 'trackajob-import' || !data.job) return
      try {
        ev.source?.postMessage({ type: 'trackajob-import-ack' }, { targetOrigin: ev.origin })
      } catch {
        /* the opener may already be closed */
      }
      history.replaceState(null, '', '#/applications')
      setPendingImport(data.job)
      navigate({ name: 'applications' }, { replace: true })
    }
    window.addEventListener('message', receiveImport)
    return () => window.removeEventListener('message', receiveImport)
  }, [navigate])

  async function logout() {
    await api('/api/auth/logout', { method: 'POST' }).catch(() => {})
    onSignedOut()
  }

  const activeTab =
    route.name === 'applications' ? 'applications' : route.name === 'stats' ? 'stats' : 'resumes'

  // On narrow screens the nav scrolls horizontally. Keep the active tab in
  // view so the current section is never half-hidden.
  useEffect(() => {
    const el = document.querySelector<HTMLElement>('.nav-link[aria-current="page"]')
    el?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  }, [activeTab])

  return (
    <>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="app-header">
        <a
          className="brand"
          href="#/resumes"
          onClick={(e) => {
            e.preventDefault()
            navigate({ name: 'resumes' })
          }}
        >
          <span className="brand-mark" aria-hidden="true">
            T
          </span>
          <span className="brand-name">TrackAJob</span>
        </a>

        <nav className="app-nav" aria-label="Main">
          <a
            className="nav-link"
            href="#/resumes"
            aria-current={activeTab === 'resumes' ? 'page' : undefined}
            onClick={(e) => {
              e.preventDefault()
              navigate({ name: 'resumes' })
            }}
          >
            Resumes
            {resumes && resumes.length > 0 && <span className="nav-count">{resumes.length}</span>}
          </a>
          <a
            className="nav-link"
            href="#/applications"
            aria-current={activeTab === 'applications' ? 'page' : undefined}
            onClick={(e) => {
              e.preventDefault()
              navigate({ name: 'applications' })
            }}
          >
            Applications
          </a>
          <a
            className="nav-link"
            href="#/stats"
            aria-current={activeTab === 'stats' ? 'page' : undefined}
            onClick={(e) => {
              e.preventDefault()
              navigate({ name: 'stats' })
            }}
          >
            Statistics
          </a>
        </nav>

        <div className="app-header-right">
          <span className="user-chip" title={user.email}>
            <span className="user-email">{user.email}</span>
          </span>
          <ThemeToggle />
          <button type="button" className="btn btn-sm btn-ghost" onClick={() => setPasswordOpen(true)}>
            Password
          </button>
          <button type="button" className="btn btn-sm btn-ghost" onClick={logout}>
            Sign out
          </button>
        </div>
      </header>

      <PasswordDialog open={passwordOpen} onClose={() => setPasswordOpen(false)} />

      <main id="main">
        {user.email_verified === false && (
          <VerifyBanner onVerified={onUserChanged} />
        )}
        {route.name === 'resume' ? (
          <ResumeEditor
            resumeId={route.id}
            onClose={() => {
              void refreshResumes()
              navigate({ name: 'resumes' })
            }}
            onChanged={() => void refreshResumes()}
          />
        ) : route.name === 'applications' ? (
          <JobsPanel
            resumes={resumes ?? []}
            pendingImport={pendingImport}
            onImportConsumed={() => setPendingImport(null)}
            statusFilter={route.status}
            search={route.q ?? ''}
            focusJobId={route.job}
            onQueryChange={setApplicationQuery}
          />
        ) : route.name === 'stats' ? (
          <StatsScreen />
        ) : (
          <ResumesScreen
            resumes={resumes}
            onOpen={(id) => navigate({ name: 'resume', id })}
            onChanged={refreshResumes}
          />
        )}
      </main>
    </>
  )
}

export default function App() {
  const [user, setUser] = useState<User | null>(null)
  const [authChecked, setAuthChecked] = useState(false)
  const { route } = useRoute()

  const refreshUser = useCallback(() => {
    api<User>('/api/auth/me')
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setAuthChecked(true))
  }, [])

  useEffect(() => {
    refreshUser()
  }, [refreshUser])

  // Token links work whether or not someone is signed in: a reset link may
  // be opened on a device where the session already expired. The `key` makes
  // React remount when the token changes, so a second link never inherits the
  // first one's result.
  const tokenScreen =
    route.name === 'reset-password' ? (
      <ResetPasswordScreen
        key={route.token}
        token={route.token}
        onDone={() => {
          refreshUser()
          window.location.hash = '#/resumes'
        }}
      />
    ) : route.name === 'verify-email' ? (
      <VerifyEmailScreen
        key={route.token}
        token={route.token}
        onDone={() => {
          refreshUser()
          window.location.hash = '#/resumes'
        }}
      />
    ) : null

  return (
    <ThemeProvider>
      <ToastProvider>
        {tokenScreen ? (
          tokenScreen
        ) : !authChecked ? (
          <Loading label="Starting TrackAJob…" />
        ) : user ? (
          <Shell
            user={user}
            onSignedOut={() => setUser(null)}
            onUserChanged={refreshUser}
          />
        ) : (
          <LoginScreen onSignedIn={setUser} onContinue={refreshUser} />
        )}
      </ToastProvider>
    </ThemeProvider>
  )
}
