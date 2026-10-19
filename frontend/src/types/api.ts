// Shapes returned by the Form4Clean HTTP API. Money and quantities arrive as decimal strings
// so the dashboard never shows a value the engine did not compute.

export type Decimal = string

export type QualityStatus = 'VALID' | 'WARNING' | 'REVIEW_REQUIRED' | 'INVALID'
export type Direction = 'ACQUISITION' | 'DISPOSITION' | 'UNKNOWN'
export type Category =
  | 'Market Purchase'
  | 'Market Sale'
  | 'Equity Compensation'
  | 'Derivative Exercise'
  | 'Tax-Related'
  | 'Gift or Transfer'
  | 'Conversion'
  | 'Other'
  | 'Unknown'

export interface Footnote {
  id: string
  fields: string[]
  text: string | null
}

export interface Transaction {
  transaction_id: string
  source_transaction_id: string
  accession_number: string
  form_type: string
  transaction_table: 'non_derivative' | 'derivative'
  sequence: number
  company_cik: string
  ticker: string | null
  company_name: string | null
  issuer_trading_symbol: string | null
  insider_cik: string | null
  insider_name: string | null
  insider_name_raw: string | null
  insider_role: string
  is_director: boolean | null
  is_officer: boolean | null
  is_ten_percent_owner: boolean | null
  is_other_reporting_owner: boolean | null
  officer_title: string | null
  other_relationship_text: string | null
  reporting_owners: { cik: string | null; name: string | null }[]
  reporting_owner_count: number
  transaction_date: string | null
  deemed_execution_date: string | null
  filing_date: string | null
  filing_timestamp: string | null
  disclosure_timing: 'PRE_MARKET' | 'MARKET_HOURS' | 'AFTER_CLOSE' | 'NON_TRADING_DAY' | 'UNKNOWN'
  disclosure_session_date: string | null
  days_to_file: number | null
  transaction_code: string | null
  transaction_type: string
  transaction_category: Category
  transaction_direction: Direction
  acquired_disposed_code: string | null
  equity_swap_involved: boolean | null
  shares: Decimal | null
  price_per_share: Decimal | null
  transaction_value: Decimal | null
  shares_owned_after: Decimal | null
  security_title: string | null
  security_title_raw: string | null
  is_derivative: boolean
  underlying_security_title: string | null
  underlying_shares: Decimal | null
  exercise_price: Decimal | null
  exercise_date: string | null
  expiration_date: string | null
  ownership_type: 'Direct' | 'Indirect' | null
  ownership_nature: string | null
  is_market_transaction: boolean | null
  is_discretionary_trade: boolean | null
  is_10b5_1: boolean | null
  is_10b5_1_source: string | null
  classification_confidence: 'HIGH' | 'MEDIUM' | 'LOW'
  classification_reason: string
  is_amended: boolean
  amendment_status: string
  amends_accession_number: string | null
  superseded_by: string | null
  is_current: boolean
  quality_status: QualityStatus
  quality_flags: string[]
  quality_explanations: string[]
  footnotes: Footnote[]
  related_transaction_ids: string[]
  sec_filing_url: string | null
  source_document: string | null
  cleaning_version: string
  schema_version: string
}

export interface TransactionList {
  count: number
  records: Transaction[]
}

export interface TransactionDetail {
  record: Transaction & { source_values: Record<string, unknown> }
  cleaning_log: {
    accession_number: string
    transaction_id: string | null
    step: string
    field: string | null
    rule: string
    before: string | null
    after: string | null
  }[]
}

export interface CompanySummary {
  cik: string
  ticker: string | null
  name: string | null
  filings: number
  transactions: number
  last_fetched: string | null
}

export interface CompanyInfo extends CompanySummary {
  coverage_start: string | null
  full_history: boolean
}

export interface Issue {
  code: string
  severity: string
  title: string
  why: string
  action: string
  review_recommended: boolean
  count: number
}

export interface QualityReport {
  company_cik: string
  ticker: string | null
  schema_version: string
  cleaning_version: string
  filings_processed: number
  filings_failed: number
  parse_failures: { accession_number: string; error: string }[]
  duplicate_filings_ignored: number
  holdings_reported: number
  filing_date_range: [string | null, string | null]
  transactions_extracted: number
  transactions_classified: number
  classification_coverage: number
  current_transactions: number
  duplicates_detected: number
  amendments: {
    amendment_filings: number
    linked: number
    original_not_found: number
    ambiguous: number
    records_superseded: number
    records_corrected: number
    records_restated: number
    records_added: number
    records_ambiguous: number
  }
  records_requiring_review: number
  status_distribution: Record<QualityStatus, number>
  category_distribution: Record<string, number>
  missing_values: Record<string, number>
  issues: Issue[]
}

export interface AmendmentLink {
  amendment_accession: string
  original_accession: string | null
  status: string
  confidence: string | null
  reason: string
  candidates: string[]
}

export interface Overview {
  window_start: string
  window_months: number
  purchases: { count: number; value: Decimal; missing_value: number }
  sales: { count: number; value: Decimal; missing_value: number; planned_10b5_1: number }
  other_count: number
  insiders: number
  records_total: number
  records_current: number
  first_transaction: string | null
  last_transaction: string | null
  top_insiders: {
    insider_cik: string | null
    insider_name: string | null
    insider_role: string
    purchased: Decimal | null
    sold: Decimal | null
    trades: number
    total: Decimal | null
  }[]
  monthly: { month: string; purchases: Decimal | null; sales: Decimal | null }[]
}

export interface PriceBar {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number | null
}

export interface PriceSeries {
  symbol: string
  provider: string
  status: 'ok' | 'unavailable' | 'error'
  message: string
  delayed: boolean
  adjusted: boolean
  retrieved_at: string | null
  bars: PriceBar[]
}

export interface Settings {
  data_directory: string
  contact_email: string | null
  user_agent: string | null
  requests_per_second: number
  price_provider: string
  tiingo_api_key_set: boolean
  csv_price_dir: string
  providers: { name: string; label: string }[]
}

export interface Job {
  id: string
  company: string
  state: 'running' | 'done' | 'error'
  stage: string
  done: number
  total: number
  message: string | null
  summary: Record<string, unknown> | null
}

export interface FlagDefinition {
  code: string
  severity: string
  title: string
  why: string
  action: string
  review_recommended: boolean
}
