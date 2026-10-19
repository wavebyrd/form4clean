import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { AppShell } from '@/components/AppShell'
import { TransactionDetailSheet } from '@/components/TransactionDetail'
import { AppStateProvider, useAppState } from '@/hooks/useAppState'
import { ChartPage } from '@/pages/ChartPage'
import { ExportPage } from '@/pages/ExportPage'
import { OverviewPage } from '@/pages/OverviewPage'
import { QualityPage } from '@/pages/QualityPage'
import { SettingsPage } from '@/pages/SettingsPage'
import { TransactionsPage } from '@/pages/TransactionsPage'

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: false } },
})

function CurrentPage() {
  const { page, ticker } = useAppState()
  return <PageFor key={`${page}:${ticker ?? ''}`} page={page} />
}

function PageFor({ page }: { page: ReturnType<typeof useAppState>['page'] }) {
  switch (page) {
    case 'chart':
      return <ChartPage />
    case 'transactions':
      return <TransactionsPage />
    case 'quality':
      return <QualityPage />
    case 'export':
      return <ExportPage />
    case 'settings':
      return <SettingsPage />
    default:
      return <OverviewPage />
  }
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppStateProvider>
        <AppShell>
          <CurrentPage />
        </AppShell>
        <TransactionDetailSheet />
      </AppStateProvider>
    </QueryClientProvider>
  )
}
