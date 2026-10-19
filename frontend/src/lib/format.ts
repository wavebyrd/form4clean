// Display formatting. Values arrive as exact decimal strings; they are converted to numbers
// only for display, never for further calculation.

const compact = new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 2 })
const whole = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 })
const exact = new Intl.NumberFormat('en-US', { maximumFractionDigits: 4 })
const usd = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 2,
})

export const DASH = '—'

export function toNumber(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null
  const n = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(n) ? n : null
}

export function fmtShares(value: string | null | undefined): string {
  const n = toNumber(value)
  return n === null ? DASH : exact.format(n)
}

export function fmtPrice(value: string | null | undefined): string {
  const n = toNumber(value)
  if (n === null) return DASH
  const digits = Math.abs(n) < 1 && n !== 0 ? 4 : 2
  return `$${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: digits })}`
}

export function fmtMoney(value: string | null | undefined): string {
  const n = toNumber(value)
  return n === null ? DASH : usd.format(n)
}

export function fmtCompactMoney(value: string | number | null | undefined): string {
  const n = toNumber(value)
  return n === null ? DASH : `$${compact.format(n)}`
}

export function fmtCount(value: number | null | undefined): string {
  return value === null || value === undefined ? DASH : whole.format(value)
}

export function fmtPct(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined ? DASH : `${(value * 100).toFixed(digits)}%`
}

export function fmtDate(value: string | null | undefined): string {
  return value ? value.slice(0, 10) : DASH
}

/** Filing timestamps are US Eastern; show them in Eastern regardless of the viewer's zone. */
export function fmtTimestamp(value: string | null | undefined): string {
  if (!value) return DASH
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  const text = d.toLocaleString('en-US', {
    timeZone: 'America/New_York',
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: 'numeric',
    minute: '2-digit',
  })
  return `${text} ET`
}

export function triState(value: boolean | null | undefined): string {
  if (value === true) return 'Yes'
  if (value === false) return 'No'
  return 'Unknown'
}

export function titleCase(text: string): string {
  return text
    .toLowerCase()
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}
