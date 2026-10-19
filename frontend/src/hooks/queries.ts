import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { api } from '@/lib/api'
import type { Filters } from '@/lib/filters'

import { useDebounced } from './useAppState'

export function useCompanies() {
  return useQuery({ queryKey: ['companies'], queryFn: api.companies })
}

export function useCompany(ticker: string | null) {
  return useQuery({
    queryKey: ['company', ticker],
    queryFn: () => api.company(ticker!),
    enabled: !!ticker,
    retry: false,
  })
}

/** Filtered transactions. Text inputs are debounced so typing does not flood the server. */
export function useTransactions(ticker: string | null, filters: Filters) {
  const debounced = useDebounced(filters, 250)
  return useQuery({
    queryKey: ['transactions', ticker, debounced],
    queryFn: () => api.transactions(ticker!, debounced),
    enabled: !!ticker,
    placeholderData: keepPreviousData,
    retry: false,
  })
}

export function useOverview(ticker: string | null) {
  return useQuery({
    queryKey: ['overview', ticker],
    queryFn: () => api.overview(ticker!),
    enabled: !!ticker,
    retry: false,
  })
}

export function useQuality(ticker: string | null) {
  return useQuery({
    queryKey: ['quality', ticker],
    queryFn: () => api.quality(ticker!),
    enabled: !!ticker,
    retry: false,
  })
}

export function usePrices(ticker: string | null, start?: string) {
  return useQuery({
    queryKey: ['prices', ticker, start],
    queryFn: () => api.prices(ticker!, start),
    enabled: !!ticker,
    staleTime: 10 * 60 * 1000,
    retry: false,
  })
}

export function useSettings() {
  return useQuery({ queryKey: ['settings'], queryFn: api.settings })
}
