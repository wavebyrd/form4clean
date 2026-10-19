// Mirrors form4clean.query.TransactionFilter. Filtering happens on the server, so the chart,
// the table and exports always see exactly the same records.

export interface Filters {
  start: string
  end: string
  date_field: 'transaction' | 'disclosure' | 'filing'
  insiders: string
  roles: string[]
  categories: string[]
  codes: string[]
  direction: '' | 'ACQUISITION' | 'DISPOSITION'
  min_value: string
  max_value: string
  min_shares: string
  derivative: '' | 'true' | 'false'
  ownership: '' | 'Direct' | 'Indirect'
  is_10b5_1: '' | 'true' | 'false' | 'unknown'
  amendment_statuses: string[]
  quality_statuses: string[]
  include_superseded: boolean
  search: string
}

export const DEFAULT_FILTERS: Filters = {
  start: '',
  end: '',
  date_field: 'transaction',
  insiders: '',
  roles: [],
  categories: [],
  codes: [],
  direction: '',
  min_value: '',
  max_value: '',
  min_shares: '',
  derivative: '',
  ownership: '',
  is_10b5_1: '',
  amendment_statuses: [],
  quality_statuses: [],
  include_superseded: false,
  search: '',
}

export const ROLES = [
  'CEO', 'CFO', 'COO', 'President', 'Chair', 'General Counsel', 'CTO', 'CAO', 'Officer',
  'Director', '10% Owner', 'Other', 'Unknown',
]

export const CATEGORIES = [
  'Market Purchase', 'Market Sale', 'Equity Compensation', 'Derivative Exercise', 'Tax-Related',
  'Gift or Transfer', 'Conversion', 'Other', 'Unknown',
]

export const CODES: { code: string; label: string }[] = [
  { code: 'P', label: 'Open market or private purchase' },
  { code: 'S', label: 'Open market or private sale' },
  { code: 'A', label: 'Grant or award' },
  { code: 'D', label: 'Disposition to issuer' },
  { code: 'F', label: 'Tax or exercise-price withholding' },
  { code: 'M', label: 'Exempt exercise or conversion' },
  { code: 'X', label: 'In-the-money exercise' },
  { code: 'O', label: 'Out-of-the-money exercise' },
  { code: 'C', label: 'Conversion' },
  { code: 'G', label: 'Gift' },
  { code: 'W', label: 'Will or inheritance' },
  { code: 'J', label: 'Other' },
  { code: 'K', label: 'Equity swap' },
  { code: 'I', label: 'Discretionary plan transaction' },
  { code: 'L', label: 'Small acquisition' },
  { code: 'E', label: 'Short derivative expiration' },
  { code: 'H', label: 'Long derivative expiration' },
  { code: 'U', label: 'Tender in change of control' },
  { code: 'Z', label: 'Voting trust' },
  { code: 'V', label: 'Voluntary early report' },
]

export const AMENDMENT_STATUSES = [
  'ORIGINAL', 'AMENDED_CORRECTED', 'AMENDED_RESTATED', 'AMENDED_ADDED', 'ORIGINAL_NOT_RESTATED',
  'AMENDMENT_ORIGINAL_NOT_FOUND', 'SUPERSEDED', 'AMENDMENT_AMBIGUOUS', 'NOT_RECONCILED',
]

export const QUALITY_STATUSES = ['VALID', 'WARNING', 'REVIEW_REQUIRED', 'INVALID']

/** Query-string parameters for the API. Unset values are omitted. */
export function filterParams(f: Filters): URLSearchParams {
  const p = new URLSearchParams()
  const set = (k: string, v: string) => {
    if (v.trim() !== '') p.set(k, v.trim())
  }
  set('start', f.start)
  set('end', f.end)
  if (f.date_field !== 'transaction') p.set('date_field', f.date_field)
  for (const term of f.insiders.split(',')) if (term.trim()) p.append('insiders', term.trim())
  for (const r of f.roles) p.append('roles', r)
  for (const c of f.categories) p.append('categories', c)
  for (const c of f.codes) p.append('codes', c)
  set('direction', f.direction)
  set('min_value', f.min_value)
  set('max_value', f.max_value)
  set('min_shares', f.min_shares)
  set('derivative', f.derivative)
  set('ownership', f.ownership)
  set('is_10b5_1', f.is_10b5_1)
  for (const s of f.amendment_statuses) p.append('amendment_statuses', s)
  for (const s of f.quality_statuses) p.append('quality_statuses', s)
  if (f.include_superseded) p.set('include_superseded', 'true')
  set('search', f.search)
  return p
}

export function activeFilterCount(f: Filters): number {
  let n = 0
  for (const key of Object.keys(DEFAULT_FILTERS) as (keyof Filters)[]) {
    const value = f[key]
    const base = DEFAULT_FILTERS[key]
    if (Array.isArray(value) ? value.length > 0 : value !== base) n += 1
  }
  return n
}

/** ISO date `years` before today (local), for range presets. */
export function yearsAgo(years: number, today = new Date()): string {
  const d = new Date(today)
  d.setFullYear(d.getFullYear() - years)
  return d.toISOString().slice(0, 10)
}
