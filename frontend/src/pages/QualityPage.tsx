import { useQuery } from '@tanstack/react-query'
import { ChevronRight, ShieldCheck } from 'lucide-react'
import * as React from 'react'

import { CategoryBadge, EmptyState, ErrorState, Kpi, SeverityBadge, StatusBadge, StatusBar } from '@/components/common'
import { Card, CardContent, CardHeader, CardTitle, Skeleton, Spinner } from '@/components/ui/primitives'
import { useQuality } from '@/hooks/queries'
import { useAppState } from '@/hooks/useAppState'
import { api } from '@/lib/api'
import { fmtCount, fmtDate, fmtMoney, fmtPct, titleCase } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Issue } from '@/types/api'

function AffectedRecords({ ticker, issue }: { ticker: string; issue: Issue }) {
  const { openTransaction } = useAppState()
  const records = useQuery({
    queryKey: ['flag', ticker, issue.code],
    queryFn: () => api.transactionsWithFlag(ticker, issue.code),
  })
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{issue.title}</CardTitle>
          <div className="mt-0.5 font-mono text-[11px] text-muted">{issue.code}</div>
        </div>
        <SeverityBadge severity={issue.severity} />
      </CardHeader>
      <CardContent className="grid gap-3 text-[13px] md:grid-cols-3">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">Why it matters</div>
          <p className="mt-1">{issue.why}</p>
        </div>
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">What the engine did</div>
          <p className="mt-1">{issue.action}</p>
        </div>
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wide text-muted">Manual review</div>
          <p className={cn('mt-1', issue.review_recommended ? 'text-warn' : 'text-muted')}>
            {issue.review_recommended ? 'Recommended. Open each record and check the source filing.' : 'Not needed.'}
          </p>
        </div>
      </CardContent>
      <div className="border-t border-border">
        {records.isPending ? (
          <div className="flex items-center gap-2 p-4 text-muted">
            <Spinner /> Loading affected records
          </div>
        ) : records.isError ? (
          <ErrorState error={records.error} className="m-4" />
        ) : (
          <table className="tabular w-full text-[12.5px]">
            <thead className="text-[11px] uppercase tracking-wide text-muted">
              <tr>
                <th className="px-4 py-2 text-left font-medium">Date</th>
                <th className="px-2 py-2 text-left font-medium">Insider</th>
                <th className="px-2 py-2 text-left font-medium">Type</th>
                <th className="px-2 py-2 text-right font-medium">Value</th>
                <th className="px-2 py-2 text-left font-medium">Explanation</th>
                <th className="px-4 py-2 text-left font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {records.data.records.map((t) => {
                const i = t.quality_flags.indexOf(issue.code)
                return (
                  <tr
                    key={t.transaction_id}
                    onClick={() => openTransaction(t.transaction_id)}
                    className="cursor-pointer border-t border-border hover:bg-accent/60"
                  >
                    <td className="px-4 py-1.5">{fmtDate(t.transaction_date)}</td>
                    <td className="px-2 py-1.5">{t.insider_name}</td>
                    <td className="px-2 py-1.5">
                      <CategoryBadge category={t.transaction_category} />
                    </td>
                    <td className="px-2 py-1.5 text-right">{fmtMoney(t.transaction_value)}</td>
                    <td className="max-w-md truncate px-2 py-1.5 text-muted" title={t.quality_explanations[i]}>
                      {t.quality_explanations[i]}
                    </td>
                    <td className="px-4 py-1.5">
                      <StatusBadge status={t.quality_status} />
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </Card>
  )
}

export function QualityPage() {
  const { ticker } = useAppState()
  const quality = useQuality(ticker)
  const [selected, setSelected] = React.useState<string | null>(null)

  if (!ticker) return <EmptyState title="Choose a company" className="flex-1" />
  if (quality.isError) return <ErrorState error={quality.error} className="m-4" />
  const r = quality.data?.report
  if (quality.isPending) {
    return (
      <div className="grid grid-cols-4 gap-3 p-4">
        {Array.from({ length: 8 }, (_, i) => (
          <Skeleton key={i} className="h-20" />
        ))}
      </div>
    )
  }
  if (!r) return <EmptyState title="No quality report yet" className="flex-1">Download filings first.</EmptyState>
  const issue = r.issues.find((i) => i.code === selected) ?? null
  const missing = Object.entries(r.missing_values).filter(([, n]) => n > 0)

  return (
    <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 xl:grid-cols-8">
        <Kpi label="Filings processed" value={fmtCount(r.filings_processed)} sub={r.filings_failed ? `${r.filings_failed} failed to parse` : 'none failed'} />
        <Kpi label="Transactions extracted" value={fmtCount(r.transactions_extracted)} sub={`${fmtCount(r.holdings_reported)} holding rows too`} />
        <Kpi label="In current view" value={fmtCount(r.current_transactions)} />
        <Kpi label="Classified" value={fmtPct(r.classification_coverage)} sub={`${fmtCount(r.transactions_classified)} records`} />
        <Kpi label="Amendments" value={fmtCount(r.amendments.amendment_filings)} sub={`${r.amendments.linked} linked · ${r.amendments.ambiguous} ambiguous`} />
        <Kpi label="Superseded" value={fmtCount(r.amendments.records_superseded)} />
        <Kpi label="Possible duplicates" value={fmtCount(r.duplicates_detected)} tone={r.duplicates_detected ? 'warn' : undefined} />
        <Kpi label="Need review" value={fmtCount(r.records_requiring_review)} tone={r.records_requiring_review ? 'warn' : undefined} />
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_340px]">
        <Card>
          <CardHeader>
            <CardTitle>Issues detected</CardTitle>
            <span className="text-xs text-muted">Click an issue to inspect the records</span>
          </CardHeader>
          {r.issues.length === 0 ? (
            <EmptyState title="No issues" icon={<ShieldCheck className="size-6 text-buy" />} />
          ) : (
            <ul>
              {r.issues.map((i) => (
                <li key={i.code} className="border-t border-border first:border-t-0">
                  <button
                    type="button"
                    onClick={() => setSelected(i.code === selected ? null : i.code)}
                    className={cn(
                      'grid w-full grid-cols-[110px_1fr_70px_16px] items-center gap-3 px-4 py-2 text-left hover:bg-accent/60',
                      selected === i.code && 'bg-accent',
                    )}
                  >
                    <SeverityBadge severity={i.severity} />
                    <span className="min-w-0">
                      <span className="block truncate text-[13px] font-medium">{i.title}</span>
                      <span className="block truncate text-xs text-muted">{i.why}</span>
                    </span>
                    <span className="tabular text-right text-[13px]">{fmtCount(i.count)}</span>
                    <ChevronRight className="size-3.5 text-muted" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Quality status</CardTitle>
            </CardHeader>
            <CardContent>
              <StatusBar distribution={r.status_distribution} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Missing values</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 text-[13px]">
              {missing.length === 0 ? (
                <div className="text-muted">No tracked field is missing.</div>
              ) : (
                missing.map(([field, n]) => (
                  <div key={field} className="flex justify-between">
                    <span className="font-mono text-xs">{field}</span>
                    <span className="tabular text-muted">
                      {fmtCount(n)} ({fmtPct(n / Math.max(1, r.transactions_extracted))})
                    </span>
                  </div>
                ))
              )}
              <p className="pt-2 text-xs text-muted">
                Missing values stay missing. Optional fields that are often blank, such as prices
                for gifts or awards, are not errors.
              </p>
            </CardContent>
          </Card>
        </div>
      </div>

      {issue ? <AffectedRecords ticker={ticker} issue={issue} /> : null}

      {quality.data?.amendment_links.length ? (
        <Card>
          <CardHeader>
            <CardTitle>Amendment reconciliation</CardTitle>
          </CardHeader>
          <table className="w-full text-[12.5px]">
            <thead className="text-[11px] uppercase tracking-wide text-muted">
              <tr>
                <th className="px-4 py-2 text-left font-medium">Amendment</th>
                <th className="px-2 py-2 text-left font-medium">Original</th>
                <th className="px-2 py-2 text-left font-medium">Outcome</th>
                <th className="px-4 py-2 text-left font-medium">Reason</th>
              </tr>
            </thead>
            <tbody>
              {quality.data.amendment_links.map((l) => (
                <tr key={l.amendment_accession} className="border-t border-border">
                  <td className="px-4 py-1.5 font-mono text-xs">{l.amendment_accession}</td>
                  <td className="px-2 py-1.5 font-mono text-xs">{l.original_accession ?? l.candidates.join(', ') ?? '—'}</td>
                  <td className="px-2 py-1.5">
                    {titleCase(l.status)}
                    {l.confidence ? <span className="text-muted"> · {titleCase(l.confidence)}</span> : null}
                  </td>
                  <td className="px-4 py-1.5 text-muted">{l.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      ) : null}

      {r.parse_failures.length ? (
        <Card>
          <CardHeader>
            <CardTitle>Filings that could not be parsed</CardTitle>
          </CardHeader>
          <ul className="text-[13px]">
            {r.parse_failures.map((f) => (
              <li key={f.accession_number} className="border-t border-border px-4 py-1.5">
                <span className="font-mono text-xs">{f.accession_number}</span> <span className="text-muted">{f.error}</span>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      <p className="text-xs text-muted">
        Report from cleaning version {r.cleaning_version}, schema {r.schema_version}. Filings dated {fmtDate(r.filing_date_range[0])} to{' '}
        {fmtDate(r.filing_date_range[1])}.
      </p>
    </div>
  )
}
