/** Date and number formatting. Everything goes through Intl so the app reads
 * naturally in the user's locale instead of assuming ISO strings or MM/DD. */

const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })
const dateFmt = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' })
const dateTimeFmt = new Intl.DateTimeFormat(undefined, {
  dateStyle: 'medium',
  timeStyle: 'short',
})

/** The API stores naive UTC timestamps (no trailing Z). Without this the
 * browser would read them as local time and show "3 hours ago" for a job
 * saved a second ago, so normalise before parsing. */
export function parseApiDate(iso: string): Date {
  if (!iso) return new Date(NaN)
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/.test(iso)
  return new Date(hasZone ? iso : `${iso}Z`)
}

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['year', 365 * 24 * 3600],
  ['month', 30 * 24 * 3600],
  ['week', 7 * 24 * 3600],
  ['day', 24 * 3600],
  ['hour', 3600],
  ['minute', 60],
]

export function relativeTime(iso: string): string {
  const d = parseApiDate(iso)
  if (Number.isNaN(d.getTime())) return ''
  const delta = (d.getTime() - Date.now()) / 1000
  for (const [unit, seconds] of UNITS) {
    if (Math.abs(delta) >= seconds) {
      return rtf.format(Math.round(delta / seconds), unit)
    }
  }
  return 'just now'
}

export function formatDate(iso: string): string {
  const d = parseApiDate(iso)
  return Number.isNaN(d.getTime()) ? '' : dateFmt.format(d)
}

export function formatDateTime(iso: string): string {
  const d = parseApiDate(iso)
  return Number.isNaN(d.getTime()) ? '' : dateTimeFmt.format(d)
}

const usdFmt = new Intl.NumberFormat(undefined, {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 4,
})

export function formatUsd(n: number): string {
  return usdFmt.format(Number.isFinite(n) ? n : 0)
}

const numFmt = new Intl.NumberFormat()

export function formatNumber(n: number): string {
  return numFmt.format(Number.isFinite(n) ? n : 0)
}

/** "Stripe" + "Senior Backend Engineer" -> "Senior Backend Engineer at Stripe" */
export function jobHeading(title: string, company: string): string {
  return company ? `${title} at ${company}` : title
}

export function hostnameOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return ''
  }
}

/** Adds https:// to a bare domain so a pasted "linkedin.com/jobs/1" link works. */
export function normalizeUrl(url: string): string {
  const t = url.trim()
  if (!t) return ''
  if (/^[a-z][a-z0-9+.-]*:/i.test(t)) return t
  return `https://${t}`
}
