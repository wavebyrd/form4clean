import {
  type ColumnDef,
  type ColumnFiltersState,
  type ExpandedState,
  type SortingFn,
  type SortingState,
  type VisibilityState,
  flexRender,
  getCoreRowModel,
  getExpandedRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table'
import {
  ArrowDown,
  ArrowUp,
  ChevronLeft,
  ChevronRight,
  ChevronsUpDown,
  Columns3,
  Download,
  ExternalLink,
  Maximize2,
  Minus,
  Plus,
} from 'lucide-react'
import * as React from 'react'

import { CategoryBadge, StatusBadge } from '@/components/common'
import { TransactionFacts } from '@/components/TransactionDetail'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '@/components/ui/overlays'
import { NativeSelect } from '@/components/ui/primitives'
import { exportUrl } from '@/lib/api'
import type { Filters } from '@/lib/filters'
import { DASH, fmtDate, fmtMoney, fmtPrice, fmtShares, titleCase, triState } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Transaction } from '@/types/api'

const decimalSort: SortingFn<Transaction> = (a, b, id) => {
  const x = a.getValue<string | null>(id)
  const y = b.getValue<string | null>(id)
  if (x === null && y === null) return 0
  if (x === null) return 1
  if (y === null) return -1
  return Number(x) - Number(y)
}

const textFilter = (row: { getValue: (id: string) => unknown }, id: string, value: string) =>
  String(row.getValue(id) ?? '')
    .toLowerCase()
    .includes(value.toLowerCase())

const columns: ColumnDef<Transaction>[] = [
  {
    id: 'expand',
    header: '',
    size: 40,
    enableResizing: false,
    enableSorting: false,
    enableHiding: false,
    cell: ({ row }) => (
      <button
        type="button"
        aria-label={row.getIsExpanded() ? 'Collapse row' : 'Expand row'}
        onClick={row.getToggleExpandedHandler()}
        className="rounded p-0.5 text-muted hover:bg-accent hover:text-foreground"
      >
        {row.getIsExpanded() ? <Minus className="size-3.5" /> : <Plus className="size-3.5" />}
      </button>
    ),
  },
  { accessorKey: 'transaction_date', header: 'Transaction Date', size: 112, cell: (c) => fmtDate(c.getValue<string>()) },
  { accessorKey: 'filing_date', header: 'Filing Date', size: 100, cell: (c) => fmtDate(c.getValue<string>()) },
  {
    accessorKey: 'disclosure_session_date',
    header: 'Disclosure Session',
    size: 124,
    cell: (c) => fmtDate(c.getValue<string>()),
  },
  {
    accessorKey: 'insider_name',
    header: 'Insider',
    size: 180,
    filterFn: textFilter,
    cell: (c) => <span className="font-medium">{c.getValue<string>() ?? DASH}</span>,
  },
  { accessorKey: 'insider_role', header: 'Role', size: 100, filterFn: textFilter },
  { accessorKey: 'officer_title', header: 'Officer Title', size: 160, filterFn: textFilter },
  {
    accessorKey: 'transaction_category',
    header: 'Transaction Type',
    size: 160,
    filterFn: textFilter,
    cell: ({ row }) => (
      <span className="inline-flex items-center gap-1.5">
        <span className="w-4 font-mono text-[11px] text-muted">{row.original.transaction_code}</span>
        <CategoryBadge category={row.original.transaction_category} />
      </span>
    ),
  },
  { accessorKey: 'transaction_code', header: 'Code', size: 60, filterFn: textFilter },
  {
    accessorKey: 'shares',
    header: 'Shares',
    size: 110,
    sortingFn: decimalSort,
    meta: { numeric: true },
    cell: (c) => fmtShares(c.getValue<string>()),
  },
  {
    accessorKey: 'price_per_share',
    header: 'Price',
    size: 96,
    sortingFn: decimalSort,
    meta: { numeric: true },
    cell: (c) => fmtPrice(c.getValue<string>()),
  },
  {
    accessorKey: 'transaction_value',
    header: 'Value',
    size: 124,
    sortingFn: decimalSort,
    meta: { numeric: true },
    cell: ({ row }) => (
      <span
        className={cn(
          row.original.transaction_value === null && 'text-muted',
          row.original.transaction_value !== null && row.original.transaction_direction === 'DISPOSITION' && 'text-sell',
          row.original.transaction_value !== null && row.original.transaction_direction === 'ACQUISITION' && 'text-buy',
        )}
      >
        {fmtMoney(row.original.transaction_value)}
      </span>
    ),
  },
  {
    accessorKey: 'shares_owned_after',
    header: 'Owned After',
    size: 120,
    sortingFn: decimalSort,
    meta: { numeric: true },
    cell: (c) => fmtShares(c.getValue<string>()),
  },
  { accessorKey: 'ownership_type', header: 'Ownership', size: 92, filterFn: textFilter },
  { accessorKey: 'security_title', header: 'Security', size: 170, filterFn: textFilter },
  {
    accessorKey: 'is_10b5_1',
    header: '10b5-1',
    size: 76,
    cell: (c) => triState(c.getValue<boolean | null>()),
  },
  {
    accessorKey: 'amendment_status',
    header: 'Amendment',
    size: 150,
    filterFn: textFilter,
    cell: (c) => titleCase(c.getValue<string>()),
  },
  {
    accessorKey: 'quality_status',
    header: 'Quality Status',
    size: 112,
    filterFn: textFilter,
    cell: (c) => <StatusBadge status={c.getValue<Transaction['quality_status']>()} />,
  },
  {
    accessorKey: 'accession_number',
    header: 'SEC Filing',
    size: 190,
    filterFn: textFilter,
    cell: ({ row }) =>
      row.original.sec_filing_url ? (
        <a
          href={row.original.sec_filing_url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 font-mono text-[11px] text-exercise hover:underline"
        >
          {row.original.accession_number}
          <ExternalLink className="size-3" />
        </a>
      ) : (
        row.original.accession_number
      ),
  },
]

const DEFAULT_HIDDEN: VisibilityState = {
  disclosure_session_date: false,
  officer_title: false,
  transaction_code: false,
  shares_owned_after: false,
  security_title: false,
  is_10b5_1: false,
  amendment_status: false,
  accession_number: false,
}

const FILTERABLE = new Set([
  'insider_name', 'insider_role', 'officer_title', 'transaction_category', 'transaction_code',
  'ownership_type', 'security_title', 'amendment_status', 'quality_status', 'accession_number',
])

function loadVisibility(): VisibilityState {
  try {
    const raw = localStorage.getItem('form4clean.columns')
    return raw ? { ...DEFAULT_HIDDEN, ...(JSON.parse(raw) as VisibilityState) } : DEFAULT_HIDDEN
  } catch {
    return DEFAULT_HIDDEN
  }
}

export function TransactionTable({
  data,
  ticker,
  filters,
  onOpen,
  loading,
}: {
  data: Transaction[]
  ticker: string
  filters: Filters
  onOpen: (id: string) => void
  loading?: boolean
}) {
  const [sorting, setSorting] = React.useState<SortingState>([])
  const [columnFilters, setColumnFilters] = React.useState<ColumnFiltersState>([])
  const [visibility, setVisibility] = React.useState<VisibilityState>(loadVisibility)
  const [expanded, setExpanded] = React.useState<ExpandedState>({})
  const [showColumnFilters, setShowColumnFilters] = React.useState(false)

  React.useEffect(() => {
    try {
      localStorage.setItem('form4clean.columns', JSON.stringify(visibility))
    } catch {
      /* not persisted; fine */
    }
  }, [visibility])

  const table = useReactTable({
    data,
    columns,
    state: { sorting, columnFilters, columnVisibility: visibility, expanded },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    onColumnVisibilityChange: setVisibility,
    onExpandedChange: setExpanded,
    getRowId: (row) => row.transaction_id,
    getRowCanExpand: () => true,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getExpandedRowModel: getExpandedRowModel(),
    columnResizeMode: 'onChange',
    initialState: { pagination: { pageSize: 100 } },
    autoResetPageIndex: true,
  })

  const rows = table.getRowModel().rows
  const filteredCount = table.getFilteredRowModel().rows.length
  const { pageIndex, pageSize } = table.getState().pagination

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-2">
        <Button variant={showColumnFilters ? 'secondary' : 'ghost'} size="sm" onClick={() => setShowColumnFilters((s) => !s)}>
          Column filters
          {columnFilters.length ? ` (${columnFilters.length})` : ''}
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm">
              <Columns3 /> Columns
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            {table
              .getAllLeafColumns()
              .filter((c) => c.getCanHide())
              .map((c) => (
                <DropdownMenuCheckboxItem
                  key={c.id}
                  checked={c.getIsVisible()}
                  onCheckedChange={(v) => c.toggleVisibility(v === true)}
                >
                  {String(c.columnDef.header)}
                </DropdownMenuCheckboxItem>
              ))}
          </DropdownMenuContent>
        </DropdownMenu>
        <div className="ml-auto flex items-center gap-2">
          <span className="text-xs text-muted">Export current filters:</span>
          <Button variant="secondary" size="sm" asChild>
            <a href={exportUrl(ticker, { dataset: 'clean', format: 'csv', filters })} download>
              <Download /> CSV
            </a>
          </Button>
          <Button variant="secondary" size="sm" asChild>
            <a href={exportUrl(ticker, { dataset: 'clean', format: 'parquet', filters })} download>
              <Download /> Parquet
            </a>
          </Button>
        </div>
      </div>

      <div className={cn('min-h-0 flex-1 overflow-auto', loading && 'opacity-60 transition-opacity')}>
        <table className="tabular border-separate border-spacing-0 text-[12.5px]" style={{ width: table.getTotalSize() }}>
          <thead className="sticky top-0 z-10 bg-panel">
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((h) => {
                  const numeric = (h.column.columnDef.meta as { numeric?: boolean } | undefined)?.numeric
                  const sorted = h.column.getIsSorted()
                  return (
                    <th
                      key={h.id}
                      style={{ width: h.getSize() }}
                      className="relative border-b border-border px-2 py-2 text-left align-top text-[11px] font-medium uppercase tracking-wide text-muted"
                    >
                      {h.isPlaceholder ? null : h.column.getCanSort() ? (
                        <button
                          type="button"
                          onClick={h.column.getToggleSortingHandler()}
                          className={cn('inline-flex items-center gap-1 hover:text-foreground', numeric && 'w-full justify-end')}
                        >
                          {flexRender(h.column.columnDef.header, h.getContext())}
                          {sorted === 'asc' ? <ArrowUp className="size-3" /> : sorted === 'desc' ? <ArrowDown className="size-3" /> : <ChevronsUpDown className="size-3 opacity-40" />}
                        </button>
                      ) : (
                        flexRender(h.column.columnDef.header, h.getContext())
                      )}
                      {showColumnFilters && FILTERABLE.has(h.column.id) ? (
                        <input
                          aria-label={`Filter ${String(h.column.columnDef.header)}`}
                          value={(h.column.getFilterValue() as string) ?? ''}
                          onChange={(e) => h.column.setFilterValue(e.target.value || undefined)}
                          className="mt-1 h-6 w-full rounded border border-border bg-panel-2 px-1.5 text-[11px] normal-case tracking-normal text-foreground"
                        />
                      ) : null}
                      {h.column.getCanResize() ? (
                        <div
                          onMouseDown={h.getResizeHandler()}
                          onTouchStart={h.getResizeHandler()}
                          className={cn(
                            'absolute right-0 top-0 h-full w-1 cursor-col-resize select-none hover:bg-ring',
                            h.column.getIsResizing() && 'bg-ring',
                          )}
                        />
                      ) : null}
                    </th>
                  )
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {rows.map((row) => (
              <React.Fragment key={row.id}>
                <tr
                  className={cn('group hover:bg-accent/60', !row.original.is_current && 'opacity-55')}
                  onDoubleClick={() => onOpen(row.original.transaction_id)}
                >
                  {row.getVisibleCells().map((cell) => {
                    const numeric = (cell.column.columnDef.meta as { numeric?: boolean } | undefined)?.numeric
                    return (
                      <td
                        key={cell.id}
                        style={{ width: cell.column.getSize(), maxWidth: cell.column.getSize() }}
                        className={cn(
                          'border-b border-border px-2 py-1.5',
                          cell.column.id !== 'expand' && 'truncate',
                          numeric && 'text-right',
                        )}
                      >
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    )
                  })}
                </tr>
                {row.getIsExpanded() ? (
                  <tr>
                    <td colSpan={row.getVisibleCells().length} className="border-b border-border bg-panel-2 px-10 py-3">
                      <div className="grid max-w-5xl gap-x-10 md:grid-cols-2">
                        <TransactionFacts t={row.original} />
                        <div className="space-y-3 text-[13px]">
                          {row.original.quality_explanations.length ? (
                            <div>
                              <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted">Quality checks</div>
                              <ul className="space-y-1">
                                {row.original.quality_explanations.map((e) => (
                                  <li key={e}>{e}</li>
                                ))}
                              </ul>
                            </div>
                          ) : null}
                          {row.original.footnotes.length ? (
                            <div>
                              <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted">Footnotes</div>
                              <ul className="space-y-1">
                                {row.original.footnotes.map((n) => (
                                  <li key={n.id}>
                                    <span className="font-mono text-[11px] text-muted">{n.id}</span> {n.text ?? 'Missing from filing.'}
                                  </li>
                                ))}
                              </ul>
                            </div>
                          ) : null}
                          <Button variant="secondary" size="sm" onClick={() => onOpen(row.original.transaction_id)}>
                            <Maximize2 /> Full details, cleaning log and source values
                          </Button>
                        </div>
                      </div>
                    </td>
                  </tr>
                ) : null}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center gap-3 border-t border-border px-4 py-2 text-xs text-muted">
        <span>
          {filteredCount === 0
            ? 'No rows'
            : `Rows ${(pageIndex * pageSize + 1).toLocaleString()}–${Math.min((pageIndex + 1) * pageSize, filteredCount).toLocaleString()} of ${filteredCount.toLocaleString()}`}
          {filteredCount !== data.length ? ` (column filters hide ${(data.length - filteredCount).toLocaleString()})` : ''}
        </span>
        <div className="ml-auto flex items-center gap-2">
          <NativeSelect
            aria-label="Rows per page"
            value={pageSize}
            onChange={(e) => table.setPageSize(Number(e.target.value))}
            className="h-7 w-24"
          >
            {[50, 100, 250, 500].map((n) => (
              <option key={n} value={n}>
                {n} / page
              </option>
            ))}
          </NativeSelect>
          <Button variant="ghost" size="icon" onClick={() => table.previousPage()} disabled={!table.getCanPreviousPage()} aria-label="Previous page">
            <ChevronLeft />
          </Button>
          <span>
            Page {pageIndex + 1} of {Math.max(1, table.getPageCount())}
          </span>
          <Button variant="ghost" size="icon" onClick={() => table.nextPage()} disabled={!table.getCanNextPage()} aria-label="Next page">
            <ChevronRight />
          </Button>
        </div>
      </div>
    </div>
  )
}
