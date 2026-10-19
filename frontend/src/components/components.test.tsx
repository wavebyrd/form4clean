import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type * as React from 'react'
import { describe, expect, it, vi } from 'vitest'

import { AppStateProvider, useAppState } from '@/hooks/useAppState'
import { DEFAULT_FILTERS } from '@/lib/filters'
import { tx } from '@/test/fixtures'

import { StatusBadge } from './common'
import { FilterBar } from './FilterBar'
import { TransactionFacts, disclosureNote } from './TransactionDetail'
import { TransactionTable } from './TransactionTable'

function WithState({ children }: { children: React.ReactNode }) {
  return <AppStateProvider>{children}</AppStateProvider>
}

function FiltersProbe() {
  const { filters } = useAppState()
  return <pre data-testid="filters">{JSON.stringify(filters)}</pre>
}

describe('StatusBadge', () => {
  it('labels each status', () => {
    render(<StatusBadge status="REVIEW_REQUIRED" />)
    expect(screen.getByText('Review')).toBeInTheDocument()
  })
})

describe('FilterBar', () => {
  it('updates shared filters and resets them', async () => {
    const user = userEvent.setup()
    render(
      <WithState>
        <FilterBar resultCount={42} />
        <FiltersProbe />
      </WithState>,
    )
    expect(screen.getByText('42')).toBeInTheDocument()
    const reset = screen.getByRole('button', { name: /reset/i })
    expect(reset).toBeDisabled()

    await user.type(screen.getByLabelText('Insider'), 'doe')
    await user.selectOptions(screen.getByLabelText('Side'), 'DISPOSITION')
    const state = JSON.parse(screen.getByTestId('filters').textContent!)
    expect(state.insiders).toBe('doe')
    expect(state.direction).toBe('DISPOSITION')

    await user.click(reset)
    expect(JSON.parse(screen.getByTestId('filters').textContent!)).toEqual(DEFAULT_FILTERS)
  })
})

describe('TransactionTable', () => {
  const rows = [
    tx({ transaction_id: 'a', insider_name: 'Jane A Doe', transaction_value: '614814.00' }),
    tx({ transaction_id: 'b', insider_name: 'Richard Roe', insider_role: 'CFO', transaction_value: '9000.00' }),
    tx({ transaction_id: 'c', insider_name: 'Pat Lee', transaction_value: null, price_per_share: null }),
  ]

  it('renders default columns, sorts numerically and expands rows', async () => {
    const user = userEvent.setup()
    const onOpen = vi.fn()
    render(<TransactionTable data={rows} ticker="EXRB" filters={DEFAULT_FILTERS} onOpen={onOpen} />)

    for (const header of ['Transaction Date', 'Filing Date', 'Insider', 'Role', 'Transaction Type', 'Shares', 'Price', 'Value', 'Ownership', 'Quality Status']) {
      expect(screen.getByRole('columnheader', { name: new RegExp(header) })).toBeInTheDocument()
    }

    await user.click(screen.getByRole('button', { name: /^Value/ }))
    const body = screen.getAllByRole('row').slice(1)
    expect(within(body[0]).getByText('Richard Roe')).toBeInTheDocument()
    expect(within(body[2]).getByText('Pat Lee')).toBeInTheDocument() // nulls sort last

    await user.click(screen.getAllByRole('button', { name: 'Expand row' })[0])
    await user.click(screen.getByRole('button', { name: /full details/i }))
    expect(onOpen).toHaveBeenCalledTimes(1)
  })

  it('links exports to the current filters', () => {
    render(
      <TransactionTable data={rows} ticker="EXRB" filters={{ ...DEFAULT_FILTERS, codes: ['S'] }} onOpen={() => {}} />,
    )
    const csv = screen.getByRole('link', { name: /csv/i })
    expect(csv.getAttribute('href')).toContain('codes=S')
    expect(csv.getAttribute('href')).toContain('format=csv')
  })
})

describe('TransactionFacts', () => {
  it('distinguishes the filing time from the first tradable session', () => {
    const t = tx()
    render(<TransactionFacts t={t} />)
    expect(screen.getByText(/after the market close/i)).toBeInTheDocument()
    expect(disclosureNote(t)).toContain('2025-03-06')
    expect(screen.getByRole('link', { name: /0000999101-25-000003/ })).toHaveAttribute(
      'href',
      t.sec_filing_url,
    )
  })
})
