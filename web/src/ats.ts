import { useMemo } from 'react'
import type { ResumeContent } from './types'

/** ATS guidance.

 * The layout is fixed and safe by construction (single column, standard
 * fonts, real headings, no tables or images). What actually gets resumes
 * rejected is content: empty sections, missing contact details, bullets with
 * no numbers, and skills crammed into a sentence. These checks surface that
 * while the user edits, so the export is never the first time they find out.
 *
 * Every check maps to a real ATS behaviour, not a style preference, and each
 * one says what to do about it.
 */

export type Check = {
  id: string
  level: 'error' | 'warn' | 'tip'
  title: string
  detail: string
}

const MAX_RECOMMENDED_BULLETS = 6

export function auditResume(content: ResumeContent): Check[] {
  const checks: Check[] = []

  const name = content.name.trim()
  if (!name) {
    checks.push({
      id: 'name',
      level: 'error',
      title: 'Add your full name',
      detail: 'Every ATS reads the name first. Without it the resume has no owner.',
    })
  } else if (name.split(/\s+/).length < 2) {
    checks.push({
      id: 'name-single',
      level: 'warn',
      title: 'Use your full name',
      detail: 'A single word is often parsed as a partial name or a job title.',
    })
  }

  const hasEmail = Boolean(content.email?.trim())
  if (!hasEmail) {
    checks.push({
      id: 'email',
      level: 'error',
      title: 'Add an email address',
      detail: 'Recruiters cannot contact you, and most parsers flag the resume as incomplete.',
    })
  } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(content.email!.trim())) {
    checks.push({
      id: 'email-format',
      level: 'warn',
      title: 'Check the email format',
      detail: 'It does not look like a complete address, so it may be parsed wrong.',
    })
  }

  if (!content.phone?.trim()) {
    checks.push({
      id: 'phone',
      level: 'tip',
      title: 'Add a phone number',
      detail: 'Optional, but many recruiters filter by contactability.',
    })
  }

  if (!content.summary?.trim()) {
    checks.push({
      id: 'summary',
      level: 'warn',
      title: 'Add a short summary',
      detail: 'Two or three sentences. It is the first prose an ATS indexes for keywords.',
    })
  }

  if (content.skills.length === 0) {
    checks.push({
      id: 'skills',
      level: 'error',
      title: 'Add your skills',
      detail: 'Skills are the section ATS keyword matching relies on most.',
    })
  } else if (content.skills.length < 5) {
    checks.push({
      id: 'skills-few',
      level: 'tip',
      title: 'List a few more skills',
      detail: 'Five or more gives keyword matching something to work with.',
    })
  }

  if (content.experience.length === 0) {
    checks.push({
      id: 'experience',
      level: 'error',
      title: 'Add at least one role',
      detail: 'Experience is the section recruiters and parsers weigh most.',
    })
  }

  const allBullets = content.experience.flatMap((e) => e.bullets.filter((b) => b.trim()))
  const bulletsWithNumbers = allBullets.filter((b) => /\d/.test(b))
  if (allBullets.length > 0 && bulletsWithNumbers.length === 0) {
    checks.push({
      id: 'numbers',
      level: 'warn',
      title: 'Quantify your achievements',
      detail:
        'None of your bullets contain a number. Figures like “cut latency 40%” are what make a bullet credible.',
    })
  }

  for (const [i, entry] of content.experience.entries()) {
    const label = entry.role || entry.company || `Role ${i + 1}`
    if (!entry.company.trim() || !entry.role.trim()) {
      checks.push({
        id: `entry-fields-${i}`,
        level: 'warn',
        title: `${label}: add company and role`,
        detail: 'Parsers look for both to build the work history.',
      })
    }
    if (!entry.start.trim()) {
      checks.push({
        id: `entry-dates-${i}`,
        level: 'warn',
        title: `${label}: add start date`,
        detail: 'Missing dates make the role look incomplete or unverifiable.',
      })
    }
    if (entry.bullets.filter((b) => b.trim()).length === 0) {
      checks.push({
        id: `entry-bullets-${i}`,
        level: 'warn',
        title: `${label}: add at least one achievement`,
        detail: 'A role with no bullets contributes no keywords.',
      })
    }
    if (entry.bullets.filter((b) => b.trim()).length > MAX_RECOMMENDED_BULLETS) {
      checks.push({
        id: `entry-long-${i}`,
        level: 'tip',
        title: `${label}: trim to ${MAX_RECOMMENDED_BULLETS} bullets`,
        detail: 'Longer entries push the resume past one page and dilute the strongest points.',
      })
    }
  }

  if (content.education.length === 0) {
    checks.push({
      id: 'education',
      level: 'tip',
      title: 'Add education',
      detail: 'Expected in most markets; skip it only if your experience speaks for itself.',
    })
  }

  for (const [i, link] of content.links.entries()) {
    if (link.url.trim() && !/^https?:\/\//i.test(link.url.trim())) {
      checks.push({
        id: `link-${i}`,
        level: 'tip',
        title: `Link ${i + 1}: add https://`,
        detail: 'Some parsers will not treat a bare domain as a link.',
      })
    }
  }

  return checks
}

/** The fixed layout guarantees, shown to the user so they can trust the
 * export without having to check it themselves. */
export const ATS_GUARANTEES = [
  'Single column, no tables or text boxes',
  'Standard fonts that every parser reads',
  'Real headings and list styles in DOCX',
  'Unicode text kept intact (accents, €, dashes)',
  'Same content in the PDF and the DOCX',
]

export function useResumeAudit(content: ResumeContent | null) {
  return useMemo(() => (content ? auditResume(content) : []), [content])
}

export function scoreOf(checks: Check[]): { score: number; label: string } {
  const errors = checks.filter((c) => c.level === 'error').length
  const warns = checks.filter((c) => c.level === 'warn').length
  const score = Math.max(0, 100 - errors * 25 - warns * 8)
  const label =
    score >= 90 ? 'Ready to send' : score >= 70 ? 'Almost ready' : score >= 40 ? 'Needs work' : 'Incomplete'
  return { score, label }
}
