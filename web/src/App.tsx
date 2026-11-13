import { useCallback, useEffect, useState } from 'react'
import { api, errorMessage, ResumeOut, User } from './types'
import { ResumeEditor } from './ResumeEditor'
import { ResumesScreen } from './ResumesScreen'
import { JobsPanel } from './JobsPanel'
import { LoginScreen } from './LoginScreen'
import { useRoute } from './router'
import { Loading, ToastProvider, useToast } from './ui'

type ImportPayload = Record<string, string>

function Shell({ user, onSignedOut }: { user: User; onSignedOut: () => void }) {
  const { route, navigate, setApplicationQuery } = useRoute()
  const [resumes, setResumes] = useState<ResumeOut[] | null>(null)
  const [pendingImport, setPendingImport] = useState<ImportPayload | null>(null)
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

  const activeTab = route.name === 'applications' ? 'applications' : 'resumes'

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
        </nav>

        <div className="app-header-right">
          <span className="user-chip" title={user.email}>
            <span className="user-email">{user.email}</span>
          </span>
          <button type="button" className="btn btn-sm btn-ghost" onClick={logout}>
            Sign out
          </button>
        </div>
      </header>

      <main id="main">
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

  useEffect(() => {
    api<User>('/api/auth/me')
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setAuthChecked(true))
  }, [])

  return (
    <ToastProvider>
      {!authChecked ? (
        <Loading label="Starting TrackAJob…" />
      ) : user ? (
        <Shell user={user} onSignedOut={() => setUser(null)} />
      ) : (
        <LoginScreen onSignedIn={setUser} />
      )}
    </ToastProvider>
  )
}
