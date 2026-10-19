// Turn transactions into chart markers. Several transactions on one day become one marker per
// group, but every underlying transaction is kept so the detail panel can list them.

import type { Transaction } from '@/types/api'

export type MarkerGroup = 'purchase' | 'sale' | 'exercise' | 'compensation' | 'other'
export type MarkerDateMode = 'disclosure' | 'transaction'

export const GROUP_LABEL: Record<MarkerGroup, string> = {
  purchase: 'Purchase',
  sale: 'Sale',
  exercise: 'Derivative exercise',
  compensation: 'Equity compensation',
  other: 'Other',
}

export const GROUP_COLOR_VAR: Record<MarkerGroup, string> = {
  purchase: '--buy',
  sale: '--sell',
  exercise: '--exercise',
  compensation: '--comp',
  other: '--other',
}

export function markerGroup(t: Transaction): MarkerGroup {
  switch (t.transaction_category) {
    case 'Market Purchase':
      return 'purchase'
    case 'Market Sale':
      return 'sale'
    case 'Derivative Exercise':
    case 'Conversion':
      return 'exercise'
    case 'Equity Compensation':
      return 'compensation'
    default:
      return 'other'
  }
}

/** The date a transaction is plotted on. Disclosure mode uses the first session in which the
 *  filing was public, so markers never appear before investors could have known. */
export function markerDate(t: Transaction, mode: MarkerDateMode): string | null {
  return mode === 'disclosure' ? t.disclosure_session_date : t.transaction_date
}

const DAY_MS = 24 * 60 * 60 * 1000

/** First trading date in `dates` (sorted ascending) on or after `day`. Weekend and holiday
 *  transactions move to the next session; dates outside the price history (more than
 *  `maxGapDays` from any bar) return null rather than being placed on the wrong bar. */
export function snapToSession(day: string, dates: string[], maxGapDays = 7): string | null {
  let lo = 0
  let hi = dates.length
  while (lo < hi) {
    const mid = (lo + hi) >> 1
    if (dates[mid] < day) lo = mid + 1
    else hi = mid
  }
  if (lo >= dates.length) return null
  const gap = (Date.parse(dates[lo]) - Date.parse(day)) / DAY_MS
  return gap <= maxGapDays ? dates[lo] : null
}

export interface MarkerCluster {
  time: string
  group: MarkerGroup
  transactions: Transaction[]
  shares: number
}

export function clusterMarkers(
  transactions: Transaction[],
  mode: MarkerDateMode,
  sessionDates: string[] | null,
): MarkerCluster[] {
  const map = new Map<string, MarkerCluster>()
  for (const t of transactions) {
    const raw = markerDate(t, mode)
    if (!raw) continue
    const time = sessionDates ? snapToSession(raw, sessionDates) : raw
    if (!time) continue
    const group = markerGroup(t)
    const key = `${time}|${group}`
    let cluster = map.get(key)
    if (!cluster) {
      cluster = { time, group, transactions: [], shares: 0 }
      map.set(key, cluster)
    }
    cluster.transactions.push(t)
    cluster.shares += Number(t.shares ?? 0)
  }
  return [...map.values()].sort((a, b) =>
    a.time === b.time ? a.group.localeCompare(b.group) : a.time.localeCompare(b.time),
  )
}

export function markerText(cluster: MarkerCluster): string {
  const code = cluster.transactions[0]?.transaction_code ?? '?'
  const n = cluster.transactions.length
  return n > 1 ? `${code}×${n}` : code
}
