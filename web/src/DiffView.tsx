import { ResumeContent } from './types'

/** Line diff of two resume snapshots. Bullets compare by exact string, which
 * is honest about what changed: cosmetic rewordings show as remove + add.
 * The previous version could report "No changes" while silently hiding an
 * edited role title, so every field that can differ is now compared. */
export function DiffView({ before, after }: { before: ResumeContent; after: ResumeContent }) {
  const addedSkills = after.skills.filter((s) => !before.skills.includes(s))
  const removedSkills = before.skills.filter((s) => !after.skills.includes(s))
  const summaryChanged = (before.summary ?? '') !== (after.summary ?? '')

  const experienceChanges = before.experience
    .map((bEntry, i) => {
      const aEntry = after.experience[i]
      if (!aEntry) return null
      const removed = bEntry.bullets.filter((b) => !aEntry.bullets.includes(b))
      const added = aEntry.bullets.filter((b) => !bEntry.bullets.includes(b))
      const headingChanged =
        bEntry.company !== aEntry.company ||
        bEntry.role !== aEntry.role ||
        (bEntry.start ?? '') !== (aEntry.start ?? '') ||
        (bEntry.end ?? '') !== (aEntry.end ?? '')
      if (removed.length === 0 && added.length === 0 && !headingChanged) return null
      return { bEntry, aEntry, removed, added, headingChanged }
    })
    .filter((x): x is NonNullable<typeof x> => x !== null)

  const structural =
    before.experience.length !== after.experience.length ||
    before.education.length !== after.education.length ||
    before.projects.length !== after.projects.length ||
    before.links.length !== after.links.length

  const nothingChanged =
    !summaryChanged &&
    addedSkills.length === 0 &&
    removedSkills.length === 0 &&
    experienceChanges.length === 0 &&
    !structural &&
    (before.name ?? '') === (after.name ?? '') &&
    (before.email ?? '') === (after.email ?? '') &&
    (before.phone ?? '') === (after.phone ?? '') &&
    (before.location ?? '') === (after.location ?? '')

  if (nothingChanged) {
    return (
      <p className="muted small">
        No changes were made. Try a more specific instruction, such as “emphasize backend
        work” or “shorten the summary”.
      </p>
    )
  }

  return (
    <div className="diff">
      {summaryChanged && (
        <div className="diff-block">
          <h4>Summary</h4>
          {before.summary?.trim() && (
            <span className="diff-line diff-removed">{before.summary}</span>
          )}
          {after.summary?.trim() && <span className="diff-line diff-added">{after.summary}</span>}
        </div>
      )}

      {(addedSkills.length > 0 || removedSkills.length > 0) && (
        <div className="diff-block">
          <h4>Skills</h4>
          <div className="diff-chips">
            {removedSkills.map((s) => (
              <span key={`r-${s}`} className="chip chip-removed">
                − {s}
              </span>
            ))}
            {addedSkills.map((s) => (
              <span key={`a-${s}`} className="chip chip-added">
                + {s}
              </span>
            ))}
          </div>
        </div>
      )}

      {experienceChanges.map(({ bEntry, aEntry, removed, added, headingChanged }, i) => (
        <div className="diff-block" key={i}>
          <h4>{aEntry.role || aEntry.company || `Experience ${i + 1}`}</h4>
          {headingChanged && (
            <>
              <span className="diff-line diff-removed">
                {[bEntry.company, bEntry.role].filter(Boolean).join(' — ')}{' '}
                {bEntry.start && `(${bEntry.start} – ${bEntry.end || 'Present'})`}
              </span>
              <span className="diff-line diff-added">
                {[aEntry.company, aEntry.role].filter(Boolean).join(' — ')}{' '}
                {aEntry.start && `(${aEntry.start} – ${aEntry.end || 'Present'})`}
              </span>
            </>
          )}
          {removed.map((b, j) => (
            <span key={`r-${j}`} className="diff-line diff-removed">
              {b}
            </span>
          ))}
          {added.map((b, j) => (
            <span key={`a-${j}`} className="diff-line diff-added">
              {b}
            </span>
          ))}
        </div>
      ))}

      {structural && (
        <p className="small muted">
          The number of entries changed: {before.experience.length} → {after.experience.length}{' '}
          experience, {before.education.length} → {after.education.length} education,{' '}
          {before.projects.length} → {after.projects.length} projects.
        </p>
      )}
    </div>
  )
}
