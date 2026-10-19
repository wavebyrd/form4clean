import type {
  AmendmentLink,
  CompanyInfo,
  CompanySummary,
  FlagDefinition,
  Job,
  Overview,
  PriceSeries,
  QualityReport,
  Settings,
  TransactionDetail,
  TransactionList,
} from '@/types/api'

import { type Filters, filterParams } from './filters'

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    })
  } catch {
    throw new ApiError(
      'Cannot reach the Form4Clean server. Is `form4clean dashboard` still running?',
      0,
    )
  }
  if (!response.ok) {
    let message = `Request failed (HTTP ${response.status}).`
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') message = body.detail
      else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg: string }) => d.msg).join('; ')
    } catch {
      /* keep the generic message */
    }
    throw new ApiError(message, response.status)
  }
  return (await response.json()) as T
}

const enc = encodeURIComponent

export const api = {
  companies: () => request<CompanySummary[]>('/api/companies'),
  company: (t: string) => request<CompanyInfo>(`/api/companies/${enc(t)}`),
  transactions: (t: string, f: Filters, extra: Record<string, string> = {}) => {
    const p = filterParams(f)
    for (const [k, v] of Object.entries(extra)) p.set(k, v)
    return request<TransactionList>(`/api/companies/${enc(t)}/transactions?${p}`)
  },
  transactionsWithFlag: (t: string, flag: string) =>
    request<TransactionList>(
      `/api/companies/${enc(t)}/transactions?flags=${enc(flag)}&include_superseded=true`,
    ),
  transaction: (t: string, id: string) =>
    request<TransactionDetail>(`/api/companies/${enc(t)}/transactions/${enc(id)}`),
  overview: (t: string) =>
    request<{ overview: Overview; status_distribution: Record<string, number> }>(
      `/api/companies/${enc(t)}/overview`,
    ),
  quality: (t: string) =>
    request<{ report: QualityReport | null; amendment_links: AmendmentLink[] }>(
      `/api/companies/${enc(t)}/quality`,
    ),
  prices: (t: string, start?: string) =>
    request<PriceSeries>(
      `/api/companies/${enc(t)}/prices${start ? `?start=${enc(start)}` : ''}`,
    ),
  startFetch: (t: string, years: number) =>
    request<{ job_id: string }>(`/api/companies/${enc(t)}/fetch`, {
      method: 'POST',
      body: JSON.stringify({ years }),
    }),
  job: (id: string) => request<Job>(`/api/jobs/${enc(id)}`),
  settings: () => request<Settings>('/api/settings'),
  saveSettings: (body: Partial<Record<string, string | number | null>>) =>
    request<Settings>('/api/settings', { method: 'PUT', body: JSON.stringify(body) }),
  flags: () => request<FlagDefinition[]>('/api/flags'),
}

export function exportUrl(
  ticker: string,
  options: {
    dataset: 'clean' | 'raw' | 'quality' | 'manifest'
    format: 'csv' | 'parquet' | 'json'
    filters?: Filters
    asOf?: string
  },
): string {
  const p = options.filters ? filterParams(options.filters) : new URLSearchParams()
  p.set('dataset', options.dataset)
  p.set('format', options.format)
  if (options.asOf) p.set('as_of', options.asOf)
  return `/api/companies/${enc(ticker)}/export?${p}`
}
