import { RotateCcw, Search, SlidersHorizontal } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Checkbox, Popover, PopoverContent, PopoverTrigger } from '@/components/ui/overlays'
import { Input, Label, NativeSelect } from '@/components/ui/primitives'
import { useAppState } from '@/hooks/useAppState'
import {
  AMENDMENT_STATUSES,
  CATEGORIES,
  CODES,
  QUALITY_STATUSES,
  ROLES,
  activeFilterCount,
  yearsAgo,
} from '@/lib/filters'
import { titleCase } from '@/lib/format'
import { cn } from '@/lib/utils'

function CheckList({
  options,
  value,
  onChange,
  label = (o: string) => o,
  columns = 2,
}: {
  options: string[]
  value: string[]
  onChange: (v: string[]) => void
  label?: (o: string) => string
  columns?: number
}) {
  return (
    <div className={cn('grid gap-x-3 gap-y-1.5', columns === 2 ? 'grid-cols-2' : 'grid-cols-3')}>
      {options.map((o) => {
        const id = `f-${o}`.replace(/\W+/g, '-')
        const checked = value.includes(o)
        return (
          <div key={o} className="flex items-center gap-2">
            <Checkbox
              id={id}
              checked={checked}
              onCheckedChange={(c) => onChange(c ? [...value, o] : value.filter((v) => v !== o))}
            />
            <label htmlFor={id} className="cursor-pointer truncate text-[13px]" title={label(o)}>
              {label(o)}
            </label>
          </div>
        )
      })}
    </div>
  )
}

const PRESETS: { label: string; years: number | null }[] = [
  { label: '1Y', years: 1 },
  { label: '3Y', years: 3 },
  { label: '5Y', years: 5 },
  { label: 'All', years: null },
]

export function FilterBar({ resultCount }: { resultCount?: number }) {
  const { filters: f, patchFilters, resetFilters } = useAppState()
  const active = activeFilterCount(f)
  const codeLabels = Object.fromEntries(CODES.map((c) => [c.code, `${c.code}: ${c.label}`]))

  return (
    <div className="flex flex-wrap items-end gap-2 border-b border-border bg-panel px-4 py-2.5">
      <div>
        <Label>Data range</Label>
        <div className="flex h-8 overflow-hidden rounded-md border border-border">
          {PRESETS.map((p) => {
            const start = p.years ? yearsAgo(p.years) : ''
            const on = f.start === start && f.end === ''
            return (
              <button
                key={p.label}
                type="button"
                aria-label={p.years ? `Filter to last ${p.label}` : 'All dates'}
                aria-pressed={on}
                onClick={() => patchFilters({ start, end: '' })}
                className={cn(
                  'px-2.5 text-xs font-medium',
                  on ? 'bg-accent text-foreground' : 'text-muted hover:text-foreground',
                )}
              >
                {p.label}
              </button>
            )
          })}
        </div>
      </div>
      <div>
        <Label htmlFor="f-start">From</Label>
        <Input id="f-start" type="date" value={f.start} onChange={(e) => patchFilters({ start: e.target.value })} className="w-36" />
      </div>
      <div>
        <Label htmlFor="f-end">To</Label>
        <Input id="f-end" type="date" value={f.end} onChange={(e) => patchFilters({ end: e.target.value })} className="w-36" />
      </div>
      <div>
        <Label htmlFor="f-datefield">Dates are</Label>
        <NativeSelect
          id="f-datefield"
          value={f.date_field}
          onChange={(e) => patchFilters({ date_field: e.target.value as typeof f.date_field })}
          className="w-36"
        >
          <option value="transaction">Transaction date</option>
          <option value="disclosure">Disclosure date</option>
          <option value="filing">Filing date</option>
        </NativeSelect>
      </div>
      <div>
        <Label htmlFor="f-side">Side</Label>
        <NativeSelect
          id="f-side"
          value={f.direction}
          onChange={(e) => patchFilters({ direction: e.target.value as typeof f.direction })}
          className="w-32"
        >
          <option value="">All</option>
          <option value="ACQUISITION">Acquisitions</option>
          <option value="DISPOSITION">Dispositions</option>
        </NativeSelect>
      </div>
      <div>
        <Label htmlFor="f-insider">Insider</Label>
        <Input
          id="f-insider"
          placeholder="Name or CIK, comma-separated"
          value={f.insiders}
          onChange={(e) => patchFilters({ insiders: e.target.value })}
          className="w-56"
        />
      </div>
      <div className="relative">
        <Label htmlFor="f-search">Search</Label>
        <Search className="pointer-events-none absolute bottom-2 left-2 size-3.5 text-muted" />
        <Input
          id="f-search"
          placeholder="Any text"
          value={f.search}
          onChange={(e) => patchFilters({ search: e.target.value })}
          className="w-44 pl-7"
        />
      </div>

      <Popover>
        <PopoverTrigger asChild>
          <Button variant="secondary">
            <SlidersHorizontal />
            More filters
            {active > 0 ? (
              <span className="rounded bg-foreground px-1 text-[10px] text-background">{active}</span>
            ) : null}
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[640px] space-y-4">
          <section>
            <Label>Insider role</Label>
            <CheckList options={ROLES} value={f.roles} onChange={(roles) => patchFilters({ roles })} columns={3} />
          </section>
          <section>
            <Label>Transaction type</Label>
            <CheckList
              options={CATEGORIES}
              value={f.categories}
              onChange={(categories) => patchFilters({ categories })}
              columns={3}
            />
          </section>
          <section>
            <Label>SEC transaction code</Label>
            <CheckList
              options={CODES.map((c) => c.code)}
              value={f.codes}
              onChange={(codes) => patchFilters({ codes })}
              label={(c) => codeLabels[c] ?? c}
              columns={2}
            />
          </section>
          <section className="grid grid-cols-3 gap-3">
            <div>
              <Label htmlFor="f-minv">Min value ($)</Label>
              <Input id="f-minv" inputMode="decimal" value={f.min_value} onChange={(e) => patchFilters({ min_value: e.target.value.replace(/[^\d.]/g, '') })} />
            </div>
            <div>
              <Label htmlFor="f-maxv">Max value ($)</Label>
              <Input id="f-maxv" inputMode="decimal" value={f.max_value} onChange={(e) => patchFilters({ max_value: e.target.value.replace(/[^\d.]/g, '') })} />
            </div>
            <div>
              <Label htmlFor="f-mins">Min shares</Label>
              <Input id="f-mins" inputMode="decimal" value={f.min_shares} onChange={(e) => patchFilters({ min_shares: e.target.value.replace(/[^\d.]/g, '') })} />
            </div>
            <div>
              <Label htmlFor="f-deriv">Security</Label>
              <NativeSelect id="f-deriv" value={f.derivative} onChange={(e) => patchFilters({ derivative: e.target.value as typeof f.derivative })}>
                <option value="">All</option>
                <option value="false">Non-derivative (Table I)</option>
                <option value="true">Derivative (Table II)</option>
              </NativeSelect>
            </div>
            <div>
              <Label htmlFor="f-own">Ownership</Label>
              <NativeSelect id="f-own" value={f.ownership} onChange={(e) => patchFilters({ ownership: e.target.value as typeof f.ownership })}>
                <option value="">All</option>
                <option value="Direct">Direct</option>
                <option value="Indirect">Indirect</option>
              </NativeSelect>
            </div>
            <div>
              <Label htmlFor="f-plan">Rule 10b5-1 plan</Label>
              <NativeSelect id="f-plan" value={f.is_10b5_1} onChange={(e) => patchFilters({ is_10b5_1: e.target.value as typeof f.is_10b5_1 })}>
                <option value="">All</option>
                <option value="true">Under a plan</option>
                <option value="false">Not under a plan</option>
                <option value="unknown">Unknown</option>
              </NativeSelect>
            </div>
          </section>
          <section>
            <Label>Amendment status</Label>
            <CheckList
              options={AMENDMENT_STATUSES}
              value={f.amendment_statuses}
              onChange={(amendment_statuses) => patchFilters({ amendment_statuses })}
              label={titleCase}
            />
            <div className="mt-2 flex items-center gap-2">
              <Checkbox
                id="f-superseded"
                checked={f.include_superseded}
                onCheckedChange={(c) => patchFilters({ include_superseded: c === true })}
              />
              <label htmlFor="f-superseded" className="text-[13px]">
                Include superseded and ambiguous amendment records
              </label>
            </div>
          </section>
          <section>
            <Label>Data quality</Label>
            <CheckList
              options={QUALITY_STATUSES}
              value={f.quality_statuses}
              onChange={(quality_statuses) => patchFilters({ quality_statuses })}
              label={titleCase}
              columns={3}
            />
          </section>
        </PopoverContent>
      </Popover>

      <Button variant="ghost" onClick={resetFilters} disabled={active === 0} title="Reset all filters">
        <RotateCcw />
        Reset
      </Button>
      {resultCount !== undefined ? (
        <div className="ml-auto self-center text-xs text-muted">
          <span className="tabular text-foreground">{resultCount.toLocaleString()}</span> matching
          transactions
        </div>
      ) : null}
    </div>
  )
}
