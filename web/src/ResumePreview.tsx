import { ResumeContent } from './types'

export function ResumePreview({ content }: { content: ResumeContent }) {
  const contact = [content.email, content.phone, content.location].filter(Boolean).join(' | ')

  const Section = ({ title, children }: { title: string; children?: React.ReactNode }) =>
    children ? (
      <section className="rt-section">
        <h2>{title.toUpperCase()}</h2>
        <hr />
        {children}
      </section>
    ) : null

  return (
    <article className="rt-page" aria-label="Resume preview">
      <header>
        <h1>{content.name || 'Your Name'}</h1>
        {contact && <p className="rt-contact">{contact}</p>}
        {content.links.length > 0 && (
          <p className="rt-contact">
            {content.links.map((l) => `${l.label}: ${l.url}`).join(' | ')}
          </p>
        )}
      </header>
      <Section title="Summary">
        {content.summary ? <p>{content.summary}</p> : undefined}
      </Section>
      <Section title="Skills">
        {content.skills.length > 0 ? <p>{content.skills.join(', ')}</p> : undefined}
      </Section>
      <Section title="Experience">
        {content.experience.length > 0 ? (
          content.experience.map((e, i) => (
            <div key={i} className="rt-entry">
              <strong>
                {e.company} - {e.role}
              </strong>
              <em className="rt-dates">
                {e.start} - {e.end || 'Present'}
              </em>
              <ul>
                {e.bullets.map((b, j) => (
                  <li key={j}>{b}</li>
                ))}
              </ul>
            </div>
          ))
        ) : undefined}
      </Section>
      <Section title="Education">
        {content.education.length > 0 ? (
          content.education.map((e, i) => (
            <div key={i}>
              <strong>
                {e.school} - {e.degree}
              </strong>
              {e.year ? ` (${e.year})` : ''}
            </div>
          ))
        ) : undefined}
      </Section>
      <Section title="Projects">
        {content.projects.length > 0 ? (
          content.projects.map((p, i) => (
            <div key={i}>
              <strong>{p.name}</strong>: {p.description}
            </div>
          ))
        ) : undefined}
      </Section>
    </article>
  )
}
