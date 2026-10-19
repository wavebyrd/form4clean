import { ArrowRight, Database, KeyRound, Search } from 'lucide-react'

import { EmptyState, ErrorState, Kpi, StatusBar } from '@/components/common'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, Skeleton } from '@/components/ui/primitives'
import { useOverview, useSettings, useTransactions } from '@/hooks/queries'
import { useAppState } from '@/hooks/useAppState'
import { DEFAULT_FILTERS } from '@/lib/filters'
import { fmtCompactMoney, fmtCount, fmtDate, fmtMoney, fmtShares, toNumber } from '@/lib/format'
import type { Overview } from '@/types/api'

function MonthlyBars({ data }: { data: Overview['monthly'] }) {
  const rows = data.slice(-36)
  const max = Math.max(1, ...rows.flatMap((r) => [toNumber(r.purchases) ?? 0, toNumber(r.sales) ?? 0]))
  if (!rows.length) {
    return <EmptyState title="No purchases or sales">Only awards, exercises and other non-trade transactions were reported.</EmptyState>
  }
  return (
    <div>
      <div className="flex h-40 items-center gap-[3px]">
        {rows.map((r) => {
          const buy = toNumber(r.purchases) ?? 0
          const sell = toNumber(r.sales) ?? 0
          return (
            <div
              key={r.month}
              className="flex h-full flex-1 flex-col"
              title={`${r.month.slice(0, 7)}: purchases ${fmtMoney(r.purchases)}, sales ${fmtMoney(r.sales)}`}
            >
              <div className="flex flex-1 items-end">
                <div className="w-full rounded-t-sm bg-buy" style={{ height: `${(100 * buy) / max}%` }} />
              </div>
              <div className="h-px bg-border" />
              <div className="flex flex-1 items-start">
                <div className="w-full rounded-b-sm bg-sell" style={{ height: `${(100 * sell) / max}%` }} />
              </div>
            </div>
          )
        })}
      </div>
      <div className="mt-1 flex justify-between text-[11px] text-muted">
        <span>{rows[0].month.slice(0, 7)}</span>
        <span>
          <span className="text-buy">▲ purchases (P)</span> · <span className="text-sell">▼ sales (S)</span> by month, dollar value
        </span>
        <span>{rows[rows.length - 1].month.slice(0, 7)}</span>
      </div>
    </div>
  )
}

function Welcome() {
  const settings = useSettings()
  const { setPage } = useAppState()
  const needsEmail = settings.data && !settings.data.contact_email
  return (
    <div className="mx-auto max-w-2xl px-6 py-16">
      <h1 className="text-xl font-semibold">Clean, standardized SEC insider trading data</h1>
      <p className="mt-2 text-muted">
        Form4Clean downloads Form 4 filings from SEC EDGAR, cleans and classifies every transaction,
        reconciles amendments, and flags anything that needs a second look.
      </p>
      <ol className="mt-8 space-y-4">
        <li className="flex gap-3">
          <KeyRound className="mt-0.5 size-4 text-muted" />
          <div>
            <div className="font-medium">Add your contact email</div>
            <div className="text-muted">
              The SEC asks automated tools to identify themselves. It is only sent to sec.gov.
            </div>
            {needsEmail ? (
              <Button size="sm" variant="secondary" className="mt-2" onClick={() => setPage('settings')}>
                Open settings <ArrowRight />
              </Button>
            ) : settings.data ? (
              <div className="mt-1 text-xs text-buy">Set: {settings.data.user_agent}</div>
            ) : null}
          </div>
        </li>
        <li className="flex gap-3">
          <Search className="mt-0.5 size-4 text-muted" />
          <div>
            <div className="font-medium">Enter a ticker or CIK above</div>
            <div className="text-muted">Then choose how many years of filings to download.</div>
          </div>
        </li>
        <li className="flex gap-3">
          <Database className="mt-0.5 size-4 text-muted" />
          <div>
            <div className="font-medium">Explore, filter and export</div>
            <div className="text-muted">Everything is stored locally in DuckDB. No account, no cloud.</div>
          </div>
        </li>
      </ol>
    </div>
  )
}

export function OverviewPage() {
  const { ticker, openTransaction, setPage } = useAppState()
  const overview = useOverview(ticker)
  const recent = useTransactions(ticker, DEFAULT_FILTERS)

  if (!ticker) return <Welcome />
  if (overview.isError) {
    return (
      <div className="p-6">
        <ErrorState error={overview.error} />
      </div>
    )
  }
  const o = overview.data?.overview
  const latest = recent.data?.records.slice(0, 12) ?? []
  const planned = o && o.sales.count ? o.sales.planned_10b5_1 / o.sales.count : null

  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-4">
      {!o ? (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
          {Array.from({ length: 5 }, (_, i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <Kpi
              label="Open market or private sales · 12M"
              value={fmtCompactMoney(o.sales.value)}
              tone="sell"
              sub={`${fmtCount(o.sales.count)} sales${o.sales.missing_value ? `, ${o.sales.missing_value} without a price` : ''}`}
            />
            <Kpi
              label="Open market or private purchases · 12M"
              value={fmtCompactMoney(o.purchases.value)}
              tone="buy"
              sub={`${fmtCount(o.purchases.count)} purchases${o.purchases.missing_value ? `, ${o.purchases.missing_value} without a price` : ''}`}
            />
            <Kpi
              label="Sales under 10b5-1 plans · 12M"
              value={planned === null ? '—' : `${Math.round(planned * 100)}%`}
              sub={`${fmtCount(o.sales.planned_10b5_1)} of ${fmtCount(o.sales.count)} sales`}
            />
            <Kpi label="Active insiders · 12M" value={fmtCount(o.insiders)} sub={`${fmtCount(o.other_count)} non-trade transactions`} />
            <Kpi
              label="Records in dataset"
              value={fmtCount(o.records_current)}
              sub={`${fmtCount(o.records_total - o.records_current)} superseded or ambiguous · ${fmtDate(o.first_transaction)} to ${fmtDate(o.last_transaction)}`}
            />
          </div>

          <div className="grid gap-4 xl:grid-cols-[1.4fr_1fr]">
            <Card>
              <CardHeader>
                <CardTitle>Purchases and sales by month</CardTitle>
                <Button variant="ghost" size="sm" onClick={() => setPage('chart')}>
                  Price chart <ArrowRight />
                </Button>
              </CardHeader>
              <CardContent>
                <MonthlyBars data={o.monthly} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Data quality</CardTitle>
                <Button variant="ghost" size="sm" onClick={() => setPage('quality')}>
                  Details <ArrowRight />
                </Button>
              </CardHeader>
              <CardContent>
                <StatusBar distribution={overview.data?.status_distribution ?? {}} />
                <p className="mt-3 text-xs text-muted">
                  Every record keeps its source values and an explanation for each flag. Nothing is
                  dropped or estimated.
                </p>
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Most active insiders · 12M (purchases and sales)</CardTitle>
              </CardHeader>
              {o.top_insiders.length ? (
                <table className="tabular w-full text-[12.5px]">
                  <thead className="text-[11px] uppercase tracking-wide text-muted">
                    <tr>
                      <th className="px-4 py-2 text-left font-medium">Insider</th>
                      <th className="px-2 py-2 text-left font-medium">Role</th>
                      <th className="px-2 py-2 text-right font-medium">Trades</th>
                      <th className="px-2 py-2 text-right font-medium">Bought</th>
                      <th className="px-4 py-2 text-right font-medium">Sold</th>
                    </tr>
                  </thead>
                  <tbody>
                    {o.top_insiders.map((r) => (
                      <tr key={r.insider_cik ?? r.insider_name} className="border-t border-border">
                        <td className="px-4 py-1.5">{r.insider_name}</td>
                        <td className="px-2 py-1.5 text-muted">{r.insider_role}</td>
                        <td className="px-2 py-1.5 text-right">{r.trades}</td>
                        <td className="px-2 py-1.5 text-right text-buy">{fmtCompactMoney(r.purchased)}</td>
                        <td className="px-4 py-1.5 text-right text-sell">{fmtCompactMoney(r.sold)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <EmptyState title="No purchases or sales in the last 12 months" />
              )}
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Latest filings</CardTitle>
                <Button variant="ghost" size="sm" onClick={() => setPage('transactions')}>
                  All transactions <ArrowRight />
                </Button>
              </CardHeader>
              <ul>
                {latest.map((t) => (
                  <li key={t.transaction_id} className="border-t border-border first:border-t-0">
                    <button
                      type="button"
                      onClick={() => openTransaction(t.transaction_id)}
                      className="tabular grid w-full grid-cols-[86px_1fr_auto] items-center gap-3 px-4 py-1.5 text-left text-[12.5px] hover:bg-accent/60"
                    >
                      <span className="text-muted">{fmtDate(t.filing_date)}</span>
                      <span className="truncate">
                        <span className="font-medium">{t.insider_name}</span>{' '}
                        <span className="text-muted">
                          {t.transaction_code} · {fmtShares(t.shares)} sh
                        </span>
                      </span>
                      <span className={t.transaction_direction === 'DISPOSITION' ? 'text-sell' : 'text-buy'}>
                        {fmtCompactMoney(t.transaction_value)}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </Card>
          </div>
        </div>
      )}
    </div>
  )
}
