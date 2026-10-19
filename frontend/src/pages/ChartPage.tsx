import { AlertTriangle, BarChart3, CandlestickChart, Clock, LineChart, MapPin } from 'lucide-react'
import * as React from 'react'

import { CategoryBadge, EmptyState, ErrorState, StatusBadge } from '@/components/common'
import { FilterBar } from '@/components/FilterBar'
import { type ChartStyle, PriceChart } from '@/components/PriceChart'
import { Button } from '@/components/ui/button'
import { Badge, Input, NativeSelect, Spinner } from '@/components/ui/primitives'
import { useCompany, usePrices, useTransactions } from '@/hooks/queries'
import { useAppState } from '@/hooks/useAppState'
import { fmtDate, fmtMoney, fmtPrice, fmtShares, fmtTimestamp } from '@/lib/format'
import {
  GROUP_COLOR_VAR,
  GROUP_LABEL,
  type MarkerCluster,
  type MarkerDateMode,
  type MarkerGroup,
  clusterMarkers,
} from '@/lib/markers'
import { cn } from '@/lib/utils'

const RANGES = ['1M', '3M', '6M', '1Y', '3Y', '5Y', 'MAX', 'Custom'] as const
type Range = (typeof RANGES)[number]

function rangeStart(range: Range, last: string): string | null {
  const d = new Date(`${last}T00:00:00Z`)
  const months: Partial<Record<Range, number>> = { '1M': 1, '3M': 3, '6M': 6, '1Y': 12, '3Y': 36, '5Y': 60 }
  const m = months[range]
  if (!m) return null
  d.setUTCMonth(d.getUTCMonth() - m)
  return d.toISOString().slice(0, 10)
}

function Toggle({
  on,
  onClick,
  children,
  title,
  label,
}: {
  on: boolean
  onClick: () => void
  children: React.ReactNode
  title?: string
  label?: string
}) {
  return (
    <button
      type="button"
      title={title}
      aria-label={label}
      aria-pressed={on}
      onClick={onClick}
      className={cn(
        'inline-flex h-7 items-center gap-1.5 rounded-md px-2 text-xs font-medium',
        on ? 'bg-accent text-foreground' : 'text-muted hover:text-foreground',
      )}
    >
      {children}
    </button>
  )
}

function ClusterPanel({ clusters, mode }: { clusters: MarkerCluster[]; mode: MarkerDateMode }) {
  const { openTransaction } = useAppState()
  if (!clusters.length) {
    return (
      <EmptyState title="Click a marker" icon={<MapPin className="size-5" />}>
        Markers group every transaction of one type on one day. Click one to see the individual
        filings behind it.
      </EmptyState>
    )
  }
  const txs = clusters.flatMap((c) => c.transactions)
  return (
    <div>
      <div className="border-b border-border px-4 py-2.5">
        <div className="text-sm font-semibold">{clusters[0].time}</div>
        <div className="text-xs text-muted">
          {txs.length} transaction{txs.length === 1 ? '' : 's'} plotted on their{' '}
          {mode === 'disclosure' ? 'first session after public disclosure' : 'transaction date'}
        </div>
      </div>
      <ul>
        {txs.map((t) => (
          <li key={t.transaction_id} className="border-b border-border">
            <button
              type="button"
              onClick={() => openTransaction(t.transaction_id)}
              className="w-full px-4 py-2.5 text-left hover:bg-accent/60"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-[13px] font-medium">{t.insider_name}</span>
                <StatusBadge status={t.quality_status} />
              </div>
              <div className="mt-0.5 text-xs text-muted">
                {t.insider_role}
                {t.officer_title ? ` · ${t.officer_title}` : ''}
              </div>
              <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                <CategoryBadge category={t.transaction_category} />
                <Badge tone="muted" className="font-mono">{t.transaction_code}</Badge>
                {t.is_derivative ? <Badge tone="exercise">Derivative</Badge> : null}
                {t.is_10b5_1 ? <Badge tone="muted">10b5-1 plan</Badge> : null}
                <Badge tone="muted">{t.ownership_type ?? 'Ownership unknown'}</Badge>
              </div>
              <div className="tabular mt-1.5 grid grid-cols-3 gap-2 text-xs">
                <span>
                  <span className="text-muted">Shares </span>
                  {fmtShares(t.shares)}
                </span>
                <span>
                  <span className="text-muted">Price </span>
                  {fmtPrice(t.price_per_share)}
                </span>
                <span>
                  <span className="text-muted">Value </span>
                  {fmtMoney(t.transaction_value)}
                </span>
              </div>
              <div className="mt-1 flex items-center gap-1 text-[11px] text-muted">
                <Clock className="size-3" />
                Traded {fmtDate(t.transaction_date)} · filed {fmtTimestamp(t.filing_timestamp)}
                {t.disclosure_timing === 'AFTER_CLOSE' ? ' (after close)' : ''}
              </div>
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function ChartPage() {
  const { ticker, filters, theme, setPage } = useAppState()
  const company = useCompany(ticker)
  const tx = useTransactions(ticker, filters)
  const priceStart = company.data?.full_history
    ? undefined
    : company.data?.coverage_start ?? undefined
  const prices = usePrices(ticker, priceStart)
  const [style, setStyle] = React.useState<ChartStyle>('candles')
  const [showVolume, setShowVolume] = React.useState(true)
  const [showMarkers, setShowMarkers] = React.useState(true)
  const [mode, setMode] = React.useState<MarkerDateMode>('disclosure')
  const [range, setRange] = React.useState<Range>('1Y')
  const [custom, setCustom] = React.useState({ from: '', to: '' })
  const [selected, setSelected] = React.useState<MarkerCluster[]>([])

  const bars = React.useMemo(() => prices.data?.bars ?? [], [prices.data])
  const sessionDates = React.useMemo(() => bars.map((b) => b.date), [bars])
  const clusters = React.useMemo(
    () => clusterMarkers(tx.data?.records ?? [], mode, sessionDates.length ? sessionDates : null),
    [tx.data, mode, sessionDates],
  )
  const shownSelection = selected.filter((c) => clusters.includes(c))

  const last = bars.length ? bars[bars.length - 1].date : null
  const visibleRange = React.useMemo(() => {
    if (!last) return null
    if (range === 'Custom') return custom.from && custom.to ? custom : null
    const from = rangeStart(range, last)
    return from ? { from, to: last } : null
  }, [range, custom, last])

  if (!ticker) {
    return <EmptyState title="Choose a company" className="flex-1">Enter a ticker above to see its price chart and insider activity.</EmptyState>
  }

  const groups = (Object.keys(GROUP_LABEL) as MarkerGroup[]).map((g) => ({
    g,
    n: clusters.filter((c) => c.group === g).reduce((a, c) => a + c.transactions.length, 0),
  }))
  const unplaced = (tx.data?.records.length ?? 0) - clusters.reduce((a, c) => a + c.transactions.length, 0)

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <FilterBar resultCount={tx.data?.count} />
      <div className="flex flex-wrap items-center gap-1 border-b border-border px-4 py-1.5">
        <Toggle on={style === 'candles'} onClick={() => setStyle('candles')} title="Candlesticks">
          <CandlestickChart className="size-3.5" /> Candles
        </Toggle>
        <Toggle on={style === 'line'} onClick={() => setStyle('line')} title="Line (close)">
          <LineChart className="size-3.5" /> Line
        </Toggle>
        <span className="mx-1 h-4 w-px bg-border" />
        <Toggle on={showVolume} onClick={() => setShowVolume((v) => !v)}>
          <BarChart3 className="size-3.5" /> Volume
        </Toggle>
        <Toggle on={showMarkers} onClick={() => setShowMarkers((v) => !v)}>
          <MapPin className="size-3.5" /> Insider markers
        </Toggle>
        <NativeSelect
          aria-label="Marker date"
          value={mode}
          onChange={(e) => setMode(e.target.value as MarkerDateMode)}
          className="ml-1 h-7 w-56 text-xs"
        >
          <option value="disclosure">Plot on public disclosure date</option>
          <option value="transaction">Plot on transaction date</option>
        </NativeSelect>
        <span className="mx-1 h-4 w-px bg-border" />
        <span className="px-1 text-[11px] uppercase tracking-wide text-muted">Zoom</span>
        {RANGES.map((r) => (
          <Toggle key={r} on={range === r} onClick={() => setRange(r)} label={`Zoom to ${r}`}>
            {r}
          </Toggle>
        ))}
        {range === 'Custom' ? (
          <span className="ml-1 flex items-center gap-1">
            <Input type="date" aria-label="Chart from" value={custom.from} onChange={(e) => setCustom((c) => ({ ...c, from: e.target.value }))} className="h-7 w-36 text-xs" />
            <Input type="date" aria-label="Chart to" value={custom.to} onChange={(e) => setCustom((c) => ({ ...c, to: e.target.value }))} className="h-7 w-36 text-xs" />
          </span>
        ) : null}
      </div>

      <div className="flex min-h-0 flex-1">
        <div className="flex min-w-0 flex-1 flex-col">
          {prices.data ? (
            <div
              className={cn(
                'flex items-center gap-2 border-b border-border px-4 py-1.5 text-xs',
                prices.data.status === 'ok' ? 'text-muted' : 'bg-warn/10 text-warn',
              )}
            >
              {prices.data.status === 'ok' ? (
                <>
                  <Badge tone="muted">{prices.data.provider}</Badge>
                  {prices.data.message}
                  {mode === 'disclosure' ? (
                    <span className="ml-auto">
                      Markers sit on the first session after each filing became public; after-close filings move to the next day.
                    </span>
                  ) : (
                    <span className="ml-auto text-warn">
                      Transaction dates are shown; investors did not know about these trades until the filing date.
                    </span>
                  )}
                </>
              ) : (
                <>
                  <AlertTriangle className="size-3.5" />
                  Price data unavailable: {prices.data.message}
                  <Button size="sm" variant="secondary" className="ml-auto" onClick={() => setPage('settings')}>
                    Settings
                  </Button>
                </>
              )}
            </div>
          ) : null}
          <div className="relative min-h-0 flex-1">
            {prices.isPending ? (
              <div className="flex h-full items-center justify-center gap-2 text-muted">
                <Spinner /> Loading prices
              </div>
            ) : prices.isError ? (
              <ErrorState error={prices.error} className="m-4" />
            ) : bars.length ? (
              <PriceChart
                bars={bars}
                clusters={clusters}
                style={style}
                showVolume={showVolume}
                showMarkers={showMarkers}
                visibleRange={visibleRange}
                theme={theme}
                onSelectClusters={setSelected}
              />
            ) : (
              <EmptyState title="No price chart" icon={<LineChart className="size-6" />} className="h-full">
                Form4Clean never draws placeholder prices. Choose Yahoo Finance or a CSV of daily
                prices in Settings to plot insider activity on the stock chart. The
                transactions table and exports work without prices.
              </EmptyState>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-border px-4 py-1.5 text-[11px] text-muted">
            {groups.map(({ g, n }) => (
              <span key={g} className="inline-flex items-center gap-1.5">
                <span className="size-2 rounded-full" style={{ background: `var(${GROUP_COLOR_VAR[g]})` }} />
                {GROUP_LABEL[g]} <span className="tabular text-foreground">{n}</span>
              </span>
            ))}
            {bars.length && unplaced > 0 ? (
              <span className="ml-auto">
                {unplaced} {unplaced === 1 ? 'transaction falls' : 'transactions fall'} outside the price history and{' '}
                {unplaced === 1 ? 'is' : 'are'} not plotted
              </span>
            ) : null}
          </div>
        </div>
        <aside className="w-80 shrink-0 overflow-y-auto border-l border-border bg-panel">
          <ClusterPanel clusters={shownSelection} mode={mode} />
        </aside>
      </div>
    </div>
  )
}
