import { useCallback, useEffect, useState } from 'react'

/** A tiny hash router. The app is served as a single page from one Vercel
 * function, so hash routes need no server rewrite rules and keep working on
 * a hard refresh. Every screen is a real URL: Back, Forward, refresh, and
 * "open in new tab" all behave the way people expect. */
export type Route =
  | { name: 'resumes' }
  | { name: 'resume'; id: number }
  | { name: 'applications'; status?: string; q?: string; job?: number }
  | { name: 'login' }

export function parseHash(hash: string): Route {
  const raw = hash.replace(/^#\/?/, '')
  const [pathPart, queryPart] = raw.split('?')
  const segments = pathPart.split('/').filter(Boolean)
  const params = new URLSearchParams(queryPart ?? '')

  if (segments[0] === 'applications') {
    const job = Number(params.get('job'))
    return {
      name: 'applications',
      status: params.get('status') ?? undefined,
      q: params.get('q') ?? undefined,
      job: Number.isFinite(job) && job > 0 ? job : undefined,
    }
  }
  if (segments[0] === 'resumes' && segments[1]) {
    const id = Number(segments[1])
    if (Number.isFinite(id) && id > 0) return { name: 'resume', id }
  }
  if (segments[0] === 'login') return { name: 'login' }
  return { name: 'resumes' }
}

export function routeToHash(route: Route): string {
  switch (route.name) {
    case 'resume':
      return `#/resumes/${route.id}`
    case 'applications': {
      const p = new URLSearchParams()
      if (route.status && route.status !== 'all') p.set('status', route.status)
      if (route.q) p.set('q', route.q)
      if (route.job) p.set('job', String(route.job))
      const qs = p.toString()
      return `#/applications${qs ? `?${qs}` : ''}`
    }
    case 'login':
      return '#/login'
    default:
      return '#/resumes'
  }
}

export function useRoute() {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash))

  useEffect(() => {
    const onHash = () => setRoute(parseHash(window.location.hash))
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const navigate = useCallback((next: Route, opts?: { replace?: boolean }) => {
    const hash = routeToHash(next)
    if (window.location.hash === hash) return
    if (opts?.replace) {
      history.replaceState(null, '', hash)
      setRoute(parseHash(hash))
    } else {
      window.location.hash = hash
    }
  }, [])

  /** Updates only the query bits of the applications route, so filters and
   * search survive a refresh and can be shared as a link. */
  const setApplicationQuery = useCallback(
    (patch: Partial<{ status?: string; q?: string; job?: number }>) => {
      const current = parseHash(window.location.hash)
      const base =
        current.name === 'applications'
          ? current
          : ({ name: 'applications' } as Extract<Route, { name: 'applications' }>)
      const next = { ...base, ...patch }
      if (patch.job === undefined) delete next.job
      const hash = routeToHash(next)
      if (window.location.hash === hash) return
      history.replaceState(null, '', hash)
      setRoute(parseHash(hash))
    },
    []
  )

  return { route, navigate, setApplicationQuery }
}
