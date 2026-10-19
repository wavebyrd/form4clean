import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  CandlestickChart,
  Download,
  LayoutDashboard,
  Moon,
  RefreshCw,
  Search,
  Settings as SettingsIcon,
  ShieldCheck,
  Sun,
  Table2,
} from 'lucide-react'
import * as React from 'react'

import { ErrorState } from '@/components/common'
import { Button } from '@/components/ui/button'
import { Input, NativeSelect, Spinner } from '@/components/ui/primitives'
import { useCompanies, useCompany } from '@/hooks/queries'
import { type Page, useAppState } from '@/hooks/useAppState'
import { api } from '@/lib/api'
import { fmtDate } from '@/lib/format'
import { cn } from '@/lib/utils'

const NAV: { page: Page; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { page: 'overview', label: 'Overview', icon: LayoutDashboard },
  { page: 'chart', label: 'Price Chart', icon: CandlestickChart },
  { page: 'transactions', label: 'Transactions', icon: Table2 },
  { page: 'quality', label: 'Data Quality', icon: ShieldCheck },
  { page: 'export', label: 'Export', icon: Download },
  { page: 'settings', label: 'Settings', icon: SettingsIcon },
]

function FetchControl({ symbol, label }: { symbol: string; label: string }) {
  const qc = useQueryClient()
  const { setTicker } = useAppState()
  const [years, setYears] = React.useState(5)
  const [jobId, setJobId] = React.useState<string | null>(null)
  const [error, setError] = React.useState<unknown>(null)

  const job = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => api.job(jobId!),
    enabled: !!jobId,
    refetchInterval: (q) => (q.state.data?.state === 'running' || !q.state.data ? 600 : false),
  })

  React.useEffect(() => {
    const state = job.data?.state
    if (state === 'done') {
      setJobId(null)
      setTicker(symbol)
      void qc.invalidateQueries()
    } else if (state === 'error') {
      setError(new Error(job.data?.message ?? 'The download failed.'))
      setJobId(null)
    }
  }, [job.data, qc, setTicker, symbol])

  const start = async () => {
    setError(null)
    try {
      const { job_id } = await api.startFetch(symbol, years)
      setJobId(job_id)
    } catch (e) {
      setError(e)
    }
  }

  const running = !!jobId
  const d = job.data
  const pct = d && d.total ? Math.round((100 * d.done) / d.total) : null

  return (
    <div className="flex items-center gap-2">
      <NativeSelect
        aria-label="History to download"
        value={years}
        onChange={(e) => setYears(Number(e.target.value))}
        className="h-8 w-24"
        disabled={running}
      >
        {[1, 3, 5, 10, 20].map((y) => (
          <option key={y} value={y}>
            {y} {y === 1 ? 'year' : 'years'}
          </option>
        ))}
      </NativeSelect>
      <Button onClick={start} disabled={running}>
        {running ? <Spinner className="size-3.5 border-background border-t-transparent" /> : <RefreshCw />}
        {label}
      </Button>
      {running ? (
        <div className="flex min-w-48 items-center gap-2 text-xs text-muted">
          <span>{d?.stage ?? 'Starting'}</span>
          {pct !== null ? (
            <>
              <div className="h-1.5 w-24 overflow-hidden rounded-full bg-accent">
                <div className="h-full bg-buy transition-all" style={{ width: `${pct}%` }} />
              </div>
              <span className="tabular">
                {d?.done}/{d?.total}
              </span>
            </>
          ) : null}
        </div>
      ) : null}
      {error ? <ErrorState error={error} className="max-w-md py-1" /> : null}
    </div>
  )
}

function Header() {
  const { ticker, setTicker, theme, toggleTheme } = useAppState()
  const companies = useCompanies()
  const company = useCompany(ticker)
  const [pending, setPending] = React.useState<string | null>(null)

  const submit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const q = String(new FormData(e.currentTarget).get('q') ?? '').trim().toUpperCase()
    if (!q) return
    const known = companies.data?.find((c) => c.ticker === q || c.cik === q.padStart(10, '0'))
    if (known) {
      setTicker(known.ticker ?? known.cik)
      setPending(null)
    } else {
      setPending(q)
    }
  }

  const stored = !!company.data && !pending
  return (
    <header className="flex flex-wrap items-center gap-3 border-b border-border bg-panel px-4 py-2.5">
      <form key={ticker ?? ''} onSubmit={submit} className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-2.5 size-3.5 text-muted" />
        <Input
          aria-label="Ticker or CIK"
          placeholder="Ticker or CIK, e.g. NVDA"
          name="q"
          defaultValue={ticker ?? ''}
          list="known-companies"
          className="w-56 pl-8 font-mono uppercase"
        />
        <datalist id="known-companies">
          {companies.data?.map((c) => (
            <option key={c.cik} value={c.ticker ?? c.cik}>
              {c.name}
            </option>
          ))}
        </datalist>
      </form>
      {pending ? (
        <div className="flex items-center gap-2">
          <span className="text-[13px] text-muted">
            No data for <span className="font-mono text-foreground">{pending}</span> yet.
          </span>
          <FetchControl symbol={pending} label="Download from SEC" />
          <Button variant="ghost" size="sm" onClick={() => setPending(null)}>
            Cancel
          </Button>
        </div>
      ) : company.data ? (
        <>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold">
              {company.data.name}{' '}
              <span className="font-mono text-xs font-normal text-muted">
                {company.data.ticker} · CIK {company.data.cik}
              </span>
            </div>
            <div className="text-xs text-muted">
              {company.data.filings.toLocaleString()} filings ·{' '}
              {company.data.full_history ? 'full history' : `since ${fmtDate(company.data.coverage_start)}`} · updated{' '}
              {company.data.last_fetched ? new Date(company.data.last_fetched).toLocaleString() : 'never'}
            </div>
          </div>
          {stored ? <FetchControl symbol={company.data.ticker ?? company.data.cik} label="Update" /> : null}
        </>
      ) : company.isError && ticker ? (
        <div className="flex items-center gap-2">
          <span className="text-[13px] text-muted">
            No data for <span className="font-mono text-foreground">{ticker}</span> yet.
          </span>
          <FetchControl symbol={ticker} label="Download from SEC" />
        </div>
      ) : null}
      <Button variant="ghost" size="icon" className="ml-auto" onClick={toggleTheme} aria-label="Toggle theme">
        {theme === 'dark' ? <Sun /> : <Moon />}
      </Button>
    </header>
  )
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { page, setPage } = useAppState()
  return (
    <div className="flex h-full">
      <nav className="flex w-52 shrink-0 flex-col border-r border-border bg-panel">
        <div className="flex items-center gap-2 px-4 py-3.5">
          <img src="/favicon.svg" alt="" className="size-6" />
          <div>
            <div className="text-sm font-semibold leading-tight">Form4Clean</div>
            <div className="text-[11px] text-muted">SEC insider data</div>
          </div>
        </div>
        <ul className="mt-1 space-y-0.5 px-2">
          {NAV.map(({ page: p, label, icon: Icon }) => (
            <li key={p}>
              <button
                type="button"
                onClick={() => setPage(p)}
                aria-current={page === p ? 'page' : undefined}
                className={cn(
                  'flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[13px]',
                  page === p ? 'bg-accent font-medium text-foreground' : 'text-muted hover:bg-accent/60 hover:text-foreground',
                )}
              >
                <Icon className="size-4" />
                {label}
              </button>
            </li>
          ))}
        </ul>
        <div className="mt-auto px-4 py-3 text-[11px] leading-relaxed text-muted">
          Data from SEC EDGAR. A research tool, not investment advice.
        </div>
      </nav>
      <div className="flex min-w-0 flex-1 flex-col">
        <Header />
        <main className="flex min-h-0 flex-1 flex-col overflow-hidden">{children}</main>
      </div>
    </div>
  )
}
