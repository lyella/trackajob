import { ResumeContent } from './types'

// Must match app/exporters.py: the preview promises to mirror the download,
// so the separators and date formatting are kept identical to the exporter.
const DASH = ' – '

function Section({ title, children }: { title: string; children?: React.ReactNode }) {
  if (!children) return null
  return (
    <section className="rt-section">
      <h2>{title.toUpperCase()}</h2>
      <hr />
      {children}
    </section>
  )
}

/** A faithful single-column ATS-safe rendering. It deliberately mirrors what
 * the PDF export draws: no columns, no tables, no icons, standard fonts. */
export function ResumePreview({ content }: { content: ResumeContent }) {
  const contact = [content.email, content.phone, content.location].filter(Boolean).join(' | ')
  const links = content.links.filter((l) => l.label || l.url)

  return (
    <article className="rt-page" aria-label="Resume preview">
      <header>
        <h1>{content.name.trim() || 'Your Name'}</h1>
        {contact && <p className="rt-contact">{contact}</p>}
        {links.length > 0 && (
          <p className="rt-contact">
            {links.map((l) => (l.label && l.url ? `${l.label}: ${l.url}` : l.label || l.url)).join(' | ')}
          </p>
        )}
      </header>

      <Section title="Summary">
        {content.summary?.trim() ? <p>{content.summary}</p> : undefined}
      </Section>

      <Section title="Skills">
        {content.skills.length > 0 ? <p>{content.skills.join(', ')}</p> : undefined}
      </Section>

      <Section title="Experience">
        {content.experience.length > 0
          ? content.experience.map((e, i) => (
              <div key={i} className="rt-entry">
                <strong>
                  {[e.company, e.role].filter(Boolean).join(DASH) || 'New role'}
                </strong>
                {(e.start || e.end) && (
                  <div className="rt-dates">
                    {e.start || 'Start'}
                    {DASH}
                    {e.end || 'Present'}
                  </div>
                )}
                {e.bullets.filter((b) => b.trim()).length > 0 && (
                  <ul>
                    {e.bullets
                      .filter((b) => b.trim())
                      .map((b, j) => (
                        <li key={j}>{b}</li>
                      ))}
                  </ul>
                )}
              </div>
            ))
          : undefined}
      </Section>

      <Section title="Education">
        {content.education.length > 0
          ? content.education.map((e, i) => (
              <div key={i} className="rt-entry">
                <strong>{[e.school, e.degree].filter(Boolean).join(DASH) || 'New entry'}</strong>
                {e.year ? <div className="rt-dates">({e.year})</div> : null}
              </div>
            ))
          : undefined}
      </Section>

      <Section title="Projects">
        {content.projects.length > 0
          ? content.projects.map((p, i) => (
              <div key={i} className="rt-entry">
                <strong>{p.name || 'New project'}</strong>
                {p.description ? <> — {p.description}</> : null}
                {p.url ? <div className="rt-dates">{p.url}</div> : null}
              </div>
            ))
          : undefined}
      </Section>
    </article>
  )
}
