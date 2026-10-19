import { EmptyState, ErrorState } from '@/components/common'
import { FilterBar } from '@/components/FilterBar'
import { TransactionTable } from '@/components/TransactionTable'
import { Spinner } from '@/components/ui/primitives'
import { useTransactions } from '@/hooks/queries'
import { useAppState } from '@/hooks/useAppState'

export function TransactionsPage() {
  const { ticker, filters, openTransaction } = useAppState()
  const tx = useTransactions(ticker, filters)

  if (!ticker) {
    return <EmptyState title="Choose a company" className="flex-1">Enter a ticker above to load its insider transactions.</EmptyState>
  }
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <FilterBar resultCount={tx.data?.count} />
      {tx.isError ? (
        <ErrorState error={tx.error} className="m-4" />
      ) : tx.isPending ? (
        <div className="flex flex-1 items-center justify-center gap-2 text-muted">
          <Spinner /> Loading transactions
        </div>
      ) : tx.data.count === 0 ? (
        <EmptyState title="No transactions match these filters" className="flex-1">
          Try widening the date range or resetting the filters.
        </EmptyState>
      ) : (
        <TransactionTable
          data={tx.data.records}
          ticker={ticker}
          filters={filters}
          onOpen={openTransaction}
          loading={tx.isFetching}
        />
      )}
    </div>
  )
}
