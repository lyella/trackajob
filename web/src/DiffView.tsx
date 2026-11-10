import { ResumeContent } from './types'

/** Line diff of two resume snapshots. Bullets compare by exact string, which
 * is honest about what changed: cosmetic rewordings show as remove+add. */
export function DiffView({ before, after }: { before: ResumeContent; after: ResumeContent }) {
  const addedSkills = after.skills.filter((s) => !before.skills.includes(s))
  const removedSkills = before.skills.filter((s) => !after.skills.includes(s))

  return (
    <div className="diff">
      {before.summary !== after.summary && (
        <div className="diff-block">
          <h4>Summary</h4>
          <p className="removed">{before.summary}</p>
          <p className="added">{after.summary}</p>
        </div>
      )}

      {(addedSkills.length > 0 || removedSkills.length > 0) && (
        <div className="diff-block">
          <h4>Skills</h4>
          {removedSkills.map((s) => (
            <span key={`r-${s}`} className="removed chip">- {s}</span>
          ))}
          {addedSkills.map((s) => (
            <span key={`a-${s}`} className="added chip">+ {s}</span>
          ))}
        </div>
      )}

      {before.experience.map((bEntry, i) => {
        const aEntry = after.experience[i]
        if (!aEntry) return null
        const removed = bEntry.bullets.filter((b) => !aEntry.bullets.includes(b))
        const added = aEntry.bullets.filter((b) => !bEntry.bullets.includes(b))
        if (removed.length === 0 && added.length === 0) return null
        return (
          <div className="diff-block" key={i}>
            <h4>
              {bEntry.company} — {bEntry.role}
            </h4>
            {removed.map((b, j) => (
              <p key={`r-${j}`} className="removed">- {b}</p>
            ))}
            {added.map((b, j) => (
              <p key={`a-${j}`} className="added">+ {b}</p>
            ))}
          </div>
        )
      })}

      {before.experience.length === after.experience.length &&
        before.experience.every((e, i) => e.bullets.length === after.experience[i].bullets.length) &&
        before.summary === after.summary &&
        addedSkills.length === 0 &&
        removedSkills.length === 0 && <p className="muted">No changes detected.</p>}
    </div>
  )
}
