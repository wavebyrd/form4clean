import { describe, expect, it } from 'vitest'

import { tx } from '@/test/fixtures'

import { DEFAULT_FILTERS, activeFilterCount, filterParams } from './filters'
import { fmtMoney, fmtPrice, fmtShares, fmtTimestamp, toNumber, triState } from './format'
import { clusterMarkers, markerGroup, markerText, snapToSession } from './markers'

describe('filterParams', () => {
  it('omits unset filters', () => {
    expect(filterParams(DEFAULT_FILTERS).toString()).toBe('')
  })

  it('encodes lists as repeated keys and trims text', () => {
    const p = filterParams({
      ...DEFAULT_FILTERS,
      roles: ['CEO', 'CFO'],
      insiders: ' doe , 999102 ',
      min_value: '100000',
      include_superseded: true,
      date_field: 'disclosure',
    })
    expect(p.getAll('roles')).toEqual(['CEO', 'CFO'])
    expect(p.getAll('insiders')).toEqual(['doe', '999102'])
    expect(p.get('min_value')).toBe('100000')
    expect(p.get('include_superseded')).toBe('true')
    expect(p.get('date_field')).toBe('disclosure')
  })

  it('counts active filters', () => {
    expect(activeFilterCount(DEFAULT_FILTERS)).toBe(0)
    expect(activeFilterCount({ ...DEFAULT_FILTERS, codes: ['P'], search: 'x' })).toBe(2)
  })
})

describe('format', () => {
  it('formats decimal strings without inventing values', () => {
    expect(fmtMoney('614814.00')).toBe('$614,814.00')
    expect(fmtMoney(null)).toBe('—')
    expect(fmtShares('12000.0000000000')).toBe('12,000')
    expect(fmtPrice('51.2345000000')).toBe('$51.23')
    expect(fmtPrice('0.5000')).toBe('$0.50')
    expect(toNumber('abc')).toBeNull()
  })

  it('shows filing times in US Eastern', () => {
    expect(fmtTimestamp('2025-03-05T21:30:12Z')).toContain('4:30')
    expect(fmtTimestamp('2025-03-05T21:30:12Z')).toMatch(/ET$/)
  })

  it('renders three-state values', () => {
    expect(triState(true)).toBe('Yes')
    expect(triState(false)).toBe('No')
    expect(triState(null)).toBe('Unknown')
  })
})

describe('markers', () => {
  const sessions = ['2025-03-03', '2025-03-04', '2025-03-05', '2025-03-06', '2025-03-07', '2025-03-10']

  it('snaps weekend dates to the next session and drops dates outside the history', () => {
    expect(snapToSession('2025-03-08', sessions)).toBe('2025-03-10')
    expect(snapToSession('2025-03-04', sessions)).toBe('2025-03-04')
    expect(snapToSession('2025-03-20', sessions)).toBeNull()
    expect(snapToSession('2024-01-01', sessions)).toBeNull()
  })

  it('groups transactions by day and type, keeping every transaction', () => {
    const items = [
      tx({ transaction_id: 'a' }),
      tx({ transaction_id: 'b', shares: '3000' }),
      tx({ transaction_id: 'c', transaction_category: 'Market Purchase', transaction_code: 'P' }),
    ]
    const clusters = clusterMarkers(items, 'disclosure', sessions)
    expect(clusters).toHaveLength(2)
    const sale = clusters.find((c) => c.group === 'sale')!
    expect(sale.time).toBe('2025-03-06')
    expect(sale.transactions.map((t) => t.transaction_id)).toEqual(['a', 'b'])
    expect(markerText(sale)).toBe('S×2')
  })

  it('uses the disclosure session, not the trade date, by default', () => {
    const [byDisclosure] = clusterMarkers([tx()], 'disclosure', null)
    const [byTrade] = clusterMarkers([tx()], 'transaction', null)
    expect(byDisclosure.time).toBe('2025-03-06')
    expect(byTrade.time).toBe('2025-03-03')
  })

  it('maps categories to marker groups', () => {
    expect(markerGroup(tx({ transaction_category: 'Derivative Exercise' }))).toBe('exercise')
    expect(markerGroup(tx({ transaction_category: 'Equity Compensation' }))).toBe('compensation')
    expect(markerGroup(tx({ transaction_category: 'Gift or Transfer' }))).toBe('other')
  })
})
