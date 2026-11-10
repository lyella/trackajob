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
export type ResumeOut = { id: number; name: string; latest_version: number }
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

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? `HTTP ${r.status}`)
  return r.json()
}
