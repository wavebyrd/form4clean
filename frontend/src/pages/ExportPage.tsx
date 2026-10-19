import { Download, FileJson, FileSpreadsheet, Info } from 'lucide-react'
import * as React from 'react'

import { EmptyState } from '@/components/common'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, Input, Label } from '@/components/ui/primitives'
import { useTransactions } from '@/hooks/queries'
import { useAppState } from '@/hooks/useAppState'
import { exportUrl } from '@/lib/api'
import { DEFAULT_FILTERS, activeFilterCount } from '@/lib/filters'
import { cn } from '@/lib/utils'

type Dataset = 'filtered' | 'all' | 'raw' | 'quality' | 'manifest'
type Format = 'csv' | 'parquet' | 'json'

const DATASETS: { id: Dataset; title: string; body: string }[] = [
  { id: 'filtered', title: 'Filtered transactions', body: 'Cleaned records matching the filters on the Chart and Transactions pages.' },
  { id: 'all', title: 'All cleaned transactions', body: 'Every record in the current view: superseded and ambiguous amendment records excluded.' },
  { id: 'raw', title: 'Raw transactions', body: 'Every parsed row exactly as filed: source strings, no cleaning or reconciliation.' },
  { id: 'quality', title: 'Data quality report', body: 'Counts, missing values, amendment outcomes and every issue with its explanation (JSON).' },
  { id: 'manifest', title: 'Dataset manifest', body: 'Schema and cleaning versions, record count, filters, amendment policy and SHA-256 checksums (JSON).' },
]

export function ExportPage() {
  const { ticker, filters } = useAppState()
  const [dataset, setDataset] = React.useState<Dataset>('filtered')
  const [format, setFormat] = React.useState<Format>('csv')
  const [asOf, setAsOf] = React.useState('')
  const [includeSuperseded, setIncludeSuperseded] = React.useState(false)
  const filtered = useTransactions(ticker, filters)

  if (!ticker) return <EmptyState title="Choose a company" className="flex-1" />

  const usesFormat = dataset === 'filtered' || dataset === 'all' || dataset === 'raw'
  const baseFilters = dataset === 'filtered' ? filters : DEFAULT_FILTERS
  const url = exportUrl(ticker, {
    dataset: dataset === 'filtered' || dataset === 'all' ? 'clean' : dataset,
    format: usesFormat ? format : 'json',
    filters: { ...baseFilters, include_superseded: baseFilters.include_superseded || includeSuperseded },
    asOf: asOf || undefined,
  })
  const nFilters = activeFilterCount(filters)

  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-4">
      <div className="mx-auto grid max-w-5xl gap-4 lg:grid-cols-[1fr_320px]">
        <Card>
          <CardHeader>
            <CardTitle>What to export</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {DATASETS.map((d) => (
              <label
                key={d.id}
                className={cn(
                  'flex cursor-pointer gap-3 rounded-md border border-border p-3 hover:bg-accent/50',
                  dataset === d.id && 'border-foreground/40 bg-accent/60',
                )}
              >
                <input type="radio" name="dataset" className="mt-1" checked={dataset === d.id} onChange={() => setDataset(d.id)} />
                <span>
                  <span className="block text-[13px] font-medium">
                    {d.title}
                    {d.id === 'filtered' ? (
                      <span className="ml-2 text-xs font-normal text-muted">
                        {filtered.data ? `${filtered.data.count.toLocaleString()} records · ` : ''}
                        {nFilters} filter{nFilters === 1 ? '' : 's'} active
                      </span>
                    ) : null}
                  </span>
                  <span className="block text-xs text-muted">{d.body}</span>
                </span>
              </label>
            ))}
          </CardContent>
        </Card>
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Options</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label>Format</Label>
                <div className="flex gap-1">
                  {(['csv', 'parquet', 'json'] as Format[]).map((f) => (
                    <Button key={f} variant={format === f ? 'secondary' : 'ghost'} size="sm" disabled={!usesFormat} onClick={() => setFormat(f)}>
                      {f === 'json' ? <FileJson /> : <FileSpreadsheet />}
                      {f.toUpperCase()}
                    </Button>
                  ))}
                </div>
                {!usesFormat ? <p className="mt-1 text-xs text-muted">Reports and manifests are JSON.</p> : null}
              </div>
              <div>
                <Label htmlFor="asof">Point in time (optional)</Label>
                <Input id="asof" type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} disabled={dataset === 'raw'} />
                <p className="mt-1 text-xs text-muted">
                  Only filings public by the end of this day (US Eastern), reconciled with the amendments public by then. No look-ahead.
                </p>
              </div>
              <label className="flex items-center gap-2 text-[13px]">
                <input type="checkbox" checked={includeSuperseded} onChange={(e) => setIncludeSuperseded(e.target.checked)} disabled={dataset === 'raw' || dataset === 'quality'} />
                Include superseded and ambiguous records
              </label>
              <Button asChild size="lg" className="w-full">
                <a href={url} download>
                  <Download /> Download
                </a>
              </Button>
            </CardContent>
          </Card>
          <div className="flex gap-2 text-xs text-muted">
            <Info className="mt-0.5 size-3.5 shrink-0" />
            <p>
              Amounts are exact decimals: Parquet decimal columns, decimal strings in CSV and JSON. CSV
              stores list columns (flags, footnotes) as JSON text. Exports are byte-for-byte
              reproducible for the same data and cleaning version.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
