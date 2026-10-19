import * as React from 'react'

import { DEFAULT_FILTERS, type Filters } from '@/lib/filters'

export const PAGES = ['overview', 'chart', 'transactions', 'quality', 'export', 'settings'] as const
export type Page = (typeof PAGES)[number]

interface AppState {
  ticker: string | null
  setTicker: (t: string | null) => void
  page: Page
  setPage: (p: Page) => void
  filters: Filters
  setFilters: (f: Filters) => void
  patchFilters: (patch: Partial<Filters>) => void
  resetFilters: () => void
  selectedId: string | null
  openTransaction: (id: string | null) => void
  theme: 'dark' | 'light'
  toggleTheme: () => void
}

const Ctx = React.createContext<AppState | null>(null)

function readUrl(): { ticker: string | null; page: Page } {
  const p = new URLSearchParams(window.location.search)
  const page = p.get('page') as Page | null
  return {
    ticker: p.get('t')?.toUpperCase() || null,
    page: page && (PAGES as readonly string[]).includes(page) ? page : 'overview',
  }
}

function readTheme(): 'dark' | 'light' {
  try {
    return localStorage.getItem('form4clean.theme') === 'light' ? 'light' : 'dark'
  } catch {
    return 'dark'
  }
}

export function AppStateProvider({ children }: { children: React.ReactNode }) {
  const [initial] = React.useState(readUrl)
  const [ticker, setTickerState] = React.useState<string | null>(initial.ticker)
  const [page, setPageState] = React.useState<Page>(initial.page)
  const [filters, setFilters] = React.useState<Filters>(DEFAULT_FILTERS)
  const [selectedId, openTransaction] = React.useState<string | null>(null)
  const [theme, setTheme] = React.useState<'dark' | 'light'>(readTheme)

  React.useEffect(() => {
    const p = new URLSearchParams()
    if (ticker) p.set('t', ticker)
    if (page !== 'overview') p.set('page', page)
    const qs = p.toString()
    window.history.replaceState(null, '', qs ? `?${qs}` : window.location.pathname)
  }, [ticker, page])

  // The class is also switched synchronously in toggleTheme: child effects (such as the chart
  // reading CSS variables) run before this one, so they must already see the new theme.
  React.useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
    try {
      localStorage.setItem('form4clean.theme', theme)
    } catch {
      /* storage unavailable; theme still applies for this visit */
    }
  }, [theme])

  const value: AppState = {
    ticker,
    setTicker: (t) => {
      setTickerState(t ? t.toUpperCase() : null)
      setFilters(DEFAULT_FILTERS)
      openTransaction(null)
    },
    page,
    setPage: setPageState,
    filters,
    setFilters,
    patchFilters: (patch) => setFilters((f) => ({ ...f, ...patch })),
    resetFilters: () => setFilters(DEFAULT_FILTERS),
    selectedId,
    openTransaction,
    theme,
    toggleTheme: () => {
      const next = theme === 'dark' ? 'light' : 'dark'
      document.documentElement.classList.toggle('dark', next === 'dark')
      setTheme(next)
    },
  }
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useAppState(): AppState {
  const ctx = React.useContext(Ctx)
  if (!ctx) throw new Error('useAppState must be used inside AppStateProvider')
  return ctx
}

/** Debounce a fast-changing value, e.g. text typed into a filter. */
export function useDebounced<T>(value: T, ms = 250): T {
  const [debounced, setDebounced] = React.useState(value)
  React.useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), ms)
    return () => window.clearTimeout(id)
  }, [value, ms])
  return debounced
}
