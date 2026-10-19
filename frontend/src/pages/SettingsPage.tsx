import { useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Save } from 'lucide-react'
import * as React from 'react'

import { ErrorState } from '@/components/common'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, Input, Label, NativeSelect, Skeleton } from '@/components/ui/primitives'
import { useSettings } from '@/hooks/queries'
import { api } from '@/lib/api'
import type { Settings } from '@/types/api'

export function SettingsPage() {
  const settings = useSettings()
  if (settings.isPending) return <Skeleton className="m-6 h-64" />
  if (settings.isError) return <ErrorState error={settings.error} className="m-4" />
  return <SettingsForm s={settings.data} />
}

function SettingsForm({ s }: { s: Settings }) {
  const qc = useQueryClient()
  const [email, setEmail] = React.useState(s.contact_email ?? '')
  const [rate, setRate] = React.useState(String(s.requests_per_second))
  const [provider, setProvider] = React.useState(s.price_provider)
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState<unknown>(null)
  const [saved, setSaved] = React.useState(false)

  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    setSaved(false)
    try {
      await api.saveSettings({
        contact_email: email.trim() || null,
        requests_per_second: Number(rate),
        price_provider: provider,
      })
      setSaved(true)
      await qc.invalidateQueries()
    } catch (err) {
      setError(err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-4">
      <form onSubmit={save} className="mx-auto max-w-2xl space-y-4">
        <Card>
          <CardHeader>
            <CardTitle>SEC EDGAR access</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <Label htmlFor="email">Contact email</Label>
              <Input id="email" type="email" required placeholder="you@example.com" value={email} onChange={(e) => setEmail(e.target.value)} />
              <p className="mt-1 text-xs text-muted">
                The SEC requires automated tools to send a User-Agent with a contact email. It is sent only to sec.gov, as{' '}
                <span className="font-mono">{s.user_agent ?? 'Form4Clean you@example.com'}</span>. No account or API key is needed.
              </p>
            </div>
            <div>
              <Label htmlFor="rate">Requests per second</Label>
              <Input id="rate" type="number" min={0.5} max={10} step={0.5} value={rate} onChange={(e) => setRate(e.target.value)} className="w-28" />
              <p className="mt-1 text-xs text-muted">The SEC limit is 10. The default of 5 leaves headroom; requests are retried with backoff if the SEC asks to slow down.</p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Price data for the chart</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <Label htmlFor="provider">Provider</Label>
              <NativeSelect id="provider" value={provider} onChange={(e) => setProvider(e.target.value)} className="w-64">
                {s.providers.map((p) => (
                  <option key={p.name} value={p.name}>
                    {p.label}
                  </option>
                ))}
              </NativeSelect>
            </div>
            {provider === 'yahoo' ? (
              <p className="text-xs text-muted">
                No key needed, but this uses Yahoo Finance&apos;s unofficial data feed through the community yfinance
                package, which can break or be throttled when Yahoo changes it. Prices are adjusted for splits. It is not
                installed by default; install it with <span className="font-mono">pip install &quot;form4clean[yfinance]&quot;</span>.
              </p>
            ) : null}
            {provider === 'csv' ? (
              <p className="text-xs text-muted">
                Save daily prices as <span className="font-mono">{s.csv_price_dir}/TICKER.csv</span> with columns
                date, open, high, low, close and volume. Historical-data downloads from Nasdaq.com work as-is.
              </p>
            ) : null}
            <p className="text-xs text-muted">
              Prices only draw the chart. They never change the insider dataset, and Form4Clean never shows placeholder prices.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Local storage</CardTitle>
          </CardHeader>
          <CardContent className="text-[13px]">
            Filings, cleaned data and caches are stored in <span className="font-mono">{s.data_directory}</span>. Set{' '}
            <span className="font-mono">FORM4CLEAN_HOME</span> to use another folder.
          </CardContent>
        </Card>

        <div className="flex items-center gap-3">
          <Button type="submit" disabled={saving}>
            <Save /> {saving ? 'Saving' : 'Save settings'}
          </Button>
          {saved ? (
            <span className="inline-flex items-center gap-1 text-xs text-buy">
              <CheckCircle2 className="size-3.5" /> Saved
            </span>
          ) : null}
          {error ? <ErrorState error={error} className="py-1" /> : null}
        </div>
      </form>
    </div>
  )
}
