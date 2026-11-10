import { useEffect, useRef, useState } from 'react'
import {
  api,
  emptyResume,
  ResumeContent,
  ResumeDetail,
  ResumeOut,
} from './types'
import { ResumePreview } from './ResumePreview'

export function ResumeEditor({
  resume,
  onClose,
}: {
  resume: ResumeOut
  onClose: () => void
}) {
  const [detail, setDetail] = useState<ResumeDetail | null>(null)
  const [content, setContent] = useState<ResumeContent | null>(null)
  const [status, setStatus] = useState<'clean' | 'dirty' | 'saving' | 'saved' | 'error'>('clean')
  const timer = useRef<number | undefined>(undefined)

  useEffect(() => {
    api<ResumeDetail>(`/api/resumes/${resume.id}`).then((d) => {
      setDetail(d)
      setContent(JSON.parse(d.content))
    })
  }, [resume.id])

  // Debounced autosave: typing changes the working copy in place; only an
  // explicit click creates a new version.
  useEffect(() => {
    if (!content || !detail || status === 'clean') return
    setStatus('saving')
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(async () => {
      try {
        await api(`/api/resumes/${detail.id}/versions/${detail.version}`, {
          method: 'PUT',
          body: JSON.stringify(content),
        })
        setStatus('saved')
      } catch {
        setStatus('error')
      }
    }, 1200)
    return () => window.clearTimeout(timer.current)
  }, [content])

  if (!content || !detail) return <p>Loading…</p>

  const set = (patch: Partial<ResumeContent>) => {
    setStatus('dirty')
    setContent({ ...content, ...patch })
  }

  const move = <T,>(arr: T[], i: number, delta: number): T[] => {
    const j = i + delta
    if (j < 0 || j >= arr.length) return arr
    const copy = [...arr]
    ;[copy[i], copy[j]] = [copy[j], copy[i]]
    setStatus('dirty')
    return copy
  }

  const saveNewVersion = async () => {
    const meta = await api<{ version: number }>(`/api/resumes/${detail.id}/versions`, {
      method: 'POST',
      body: JSON.stringify(content),
    })
    setDetail({ ...detail, version: meta.version })
    setStatus('saved')
  }

  const info = (label: string, key: 'name' | 'email' | 'phone' | 'location') => (
    <label>
      {label}{' '}
      <input value={content[key] ?? ''} onChange={(e) => set({ [key]: e.target.value } as Partial<ResumeContent>)} />
    </label>
  )

  return (
    <div className="editor">
      <header className="editor-bar">
        <button onClick={onClose}>Back to list</button>
        <strong>{resume.name}</strong>
        <span>
          version {detail.version} — autosave: {status}
        </span>
        <button onClick={saveNewVersion} disabled={status === 'saving'}>
          Save as new version
        </button>
      </header>

      <div className="editor-panels">
        <div className="editor-form">
          <h3>Basics</h3>
          {info('Full name', 'name')}
          {info('Email', 'email')}
          {info('Phone', 'phone')}
          {info('Location', 'location')}

          <h3>Summary</h3>
          <textarea
            value={content.summary ?? ''}
            onChange={(e) => set({ summary: e.target.value })}
            rows={3}
          />

          <h3>Skills</h3>
          <input
            value={content.skills.join(', ')}
            onChange={(e) =>
              set({
                skills: e.target.value.split(',').map((s) => s.trim()).filter(Boolean),
              })
            }
            placeholder="comma separated"
          />

          <h3>Links</h3>
          {content.links.map((l, i) => (
            <div key={i} className="row">
              <input
                value={l.label}
                onChange={(e) => {
                  const links = [...content.links]
                  links[i] = { ...l, label: e.target.value }
                  set({ links })
                }}
                placeholder="label"
              />
              <input
                value={l.url}
                onChange={(e) => {
                  const links = [...content.links]
                  links[i] = { ...l, url: e.target.value }
                  set({ links })
                }}
                placeholder="url"
              />
              <button onClick={() => set({ links: content.links.filter((_, j) => j !== i) })}>x</button>
            </div>
          ))}
          <button onClick={() => set({ links: [...content.links, { label: '', url: '' }] })}>
            Add link
          </button>

          <h3>Experience</h3>
          {content.experience.map((e, i) => (
            <div key={i} className="entry">
              <div className="row">
                <button onClick={() => set({ experience: move(content.experience, i, -1) })}>↑</button>
                <button onClick={() => set({ experience: move(content.experience, i, 1) })}>↓</button>
                <strong>{e.company || 'New entry'}</strong>
                <button
                  onClick={() => set({ experience: content.experience.filter((_, j) => j !== i) })}
                >
                  x
                </button>
              </div>
              {(
                [
                  ['Company', 'company'],
                  ['Role', 'role'],
                  ['Start', 'start'],
                  ['End', 'end'],
                ] as const
              ).map(([label, key]) => (
                <label key={key}>
                  {label}{' '}
                  <input
                    value={e[key] ?? ''}
                    onChange={(ev) => {
                      const exp = [...content.experience]
                      exp[i] = { ...e, [key]: ev.target.value }
                      set({ experience: exp })
                    }}
                  />
                </label>
              ))}
              <textarea
                value={e.bullets.join('\n')}
                onChange={(ev) => {
                  const exp = [...content.experience]
                  exp[i] = { ...e, bullets: ev.target.value.split('\n') }
                  set({ experience: exp })
                }}
                rows={3}
                placeholder="one achievement per line"
              />
            </div>
          ))}
          <button
            onClick={() =>
              set({
                experience: [
                  ...content.experience,
                  { company: '', role: '', start: '', end: '', bullets: [''] },
                ],
              })
            }
          >
            Add experience
          </button>

          <h3>Education</h3>
          {content.education.map((e, i) => (
            <div key={i} className="row">
              <input
                value={e.school}
                onChange={(ev) => {
                  const edu = [...content.education]
                  edu[i] = { ...e, school: ev.target.value }
                  set({ education: edu })
                }}
                placeholder="school"
              />
              <input
                value={e.degree}
                onChange={(ev) => {
                  const edu = [...content.education]
                  edu[i] = { ...e, degree: ev.target.value }
                  set({ education: edu })
                }}
                placeholder="degree"
              />
              <button onClick={() => set({ education: content.education.filter((_, j) => j !== i) })}>x</button>
            </div>
          ))}
          <button onClick={() => set({ education: [...content.education, { school: '', degree: '' }] })}>
            Add education
          </button>

          <h3>Projects</h3>
          {content.projects.map((p, i) => (
            <div key={i} className="row">
              <input
                value={p.name}
                onChange={(ev) => {
                  const pr = [...content.projects]
                  pr[i] = { ...p, name: ev.target.value }
                  set({ projects: pr })
                }}
                placeholder="name"
              />
              <input
                value={p.description}
                onChange={(ev) => {
                  const pr = [...content.projects]
                  pr[i] = { ...p, description: ev.target.value }
                  set({ projects: pr })
                }}
                placeholder="description"
              />
              <button onClick={() => set({ projects: content.projects.filter((_, j) => j !== i) })}>x</button>
            </div>
          ))}
          <button
            onClick={() => set({ projects: [...content.projects, { name: '', description: '' }] })}
          >
            Add project
          </button>
        </div>

        <ResumePreview content={content} />
      </div>
    </div>
  )
}

export function createStarterResume(name: string) {
  return api<ResumeOut>('/api/resumes', {
    method: 'POST',
    body: JSON.stringify({ name, content: emptyResume('') }),
  })
}
