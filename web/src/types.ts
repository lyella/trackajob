export type LinkEntry = { label: string; url: string }
export type ExperienceEntry = {
  company: string
  role: string
  start: string
  end?: string
  bullets: string[]
}
export type EducationEntry = { school: string; degree: string; year?: string }
export type ProjectEntry = { name: string; description: string; url?: string }
export type ResumeContent = {
  name: string
  email?: string
  phone?: string
  location?: string
  links: LinkEntry[]
  summary?: string
  skills: string[]
  experience: ExperienceEntry[]
  education: EducationEntry[]
  projects: ProjectEntry[]
}

export type User = { id: number; email: string }
export type ResumeVersionMeta = { version: number; created_at: string }
export type ResumeOut = {
  id: number
  name: string
  latest_version: number
  versions?: ResumeVersionMeta[]
}
export type ResumeDetail = {
  id: number
  name: string
  version: number
  content: string
}

export const emptyResume = (name: string): ResumeContent => ({
  name,
  links: [],
  skills: [],
  experience: [],
  education: [],
  projects: [],
})

/** Defensive parse: stored content may predate a field being added, and a
 * missing array must not crash the editor with "cannot read map of undefined". */
export function parseResume(raw: string): ResumeContent {
  let parsed: Partial<ResumeContent> = {}
  try {
    parsed = JSON.parse(raw) as Partial<ResumeContent>
  } catch {
    parsed = {}
  }
  return {
    name: parsed.name ?? '',
    email: parsed.email ?? '',
    phone: parsed.phone ?? '',
    location: parsed.location ?? '',
    summary: parsed.summary ?? '',
    links: Array.isArray(parsed.links) ? parsed.links : [],
    skills: Array.isArray(parsed.skills) ? parsed.skills : [],
    experience: Array.isArray(parsed.experience) ? parsed.experience : [],
    education: Array.isArray(parsed.education) ? parsed.education : [],
    projects: Array.isArray(parsed.projects) ? parsed.projects : [],
  }
}

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** Turns FastAPI validation payloads (arrays of {msg, loc}) into one line a
 * person can act on, instead of "[object Object]" or a raw 422 body.
 * Also unwraps the {reason, message} shape the scraper returns, so a blocked
 * job board explains itself instead of reading "HTTP 422". */
function detailToMessage(detail: unknown, status: number): string {
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    const shaped = detail as { message?: unknown; reason?: unknown }
    if (typeof shaped.message === 'string' && shaped.message) return shaped.message
  }
  if (Array.isArray(detail)) {
    const parts = detail
      .map((d) => {
        if (!d || typeof d !== 'object') return null
        const msg = String((d as { msg?: unknown }).msg ?? '')
        const loc = (d as { loc?: unknown[] }).loc
        const field = Array.isArray(loc) ? loc[loc.length - 1] : undefined
        if (!msg) return null
        return typeof field === 'string' ? `${field}: ${msg}` : msg
      })
      .filter(Boolean)
    if (parts.length) return parts.join('; ')
  }
  return status === 401
    ? 'Your session expired. Sign in again.'
    : `Request failed (HTTP ${status}).`
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response
  try {
    r = await fetch(path, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    })
  } catch {
    throw new ApiError('Cannot reach the server. Check your connection and try again.', 0)
  }
  if (!r.ok) {
    const body = await r.json().catch(() => null)
    throw new ApiError(detailToMessage(body?.detail, r.status), r.status)
  }
  if (r.status === 204) return undefined as T
  return r.json() as Promise<T>
}

/** Human sentence for any thrown value, used by every error boundary in the UI. */
export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message
  if (e instanceof Error) return e.message
  return String(e)
}
