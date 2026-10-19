import { useQuery } from '@tanstack/react-query'
import { ExternalLink } from 'lucide-react'
import type * as React from 'react'

import { CategoryBadge, ErrorState, StatusBadge } from '@/components/common'
import { Sheet, SheetContent } from '@/components/ui/overlays'
import { Badge, Skeleton } from '@/components/ui/primitives'
import { useAppState } from '@/hooks/useAppState'
import { api } from '@/lib/api'
import {
  disclosureNote,
  fmtDate,
  fmtMoney,
  fmtPrice,
  fmtShares,
  fmtTimestamp,
  titleCase,
  triState,
} from '@/lib/format'
import type { Transaction } from '@/types/api'

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[150px_1fr] gap-3 py-1.5 text-[13px]">
      <dt className="text-muted">{label}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-b border-border px-5 py-3.5">
      <h4 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted">{title}</h4>
      {children}
    </section>
  )
}

export function TransactionFacts({ t }: { t: Transaction }) {
  return (
    <dl>
      <Row label="Insider">
        {t.insider_name ?? '—'}
        {t.insider_name_raw && t.insider_name_raw !== t.insider_name ? (
          <span className="text-muted"> (filed as “{t.insider_name_raw}”)</span>
        ) : null}
      </Row>
      <Row label="Role">
        {t.insider_role}
        {t.officer_title ? <span className="text-muted"> · {t.officer_title}</span> : null}
      </Row>
      <Row label="Transaction type">
        <span className="mr-2">{t.transaction_type}</span>
        <CategoryBadge category={t.transaction_category} />
      </Row>
      <Row label="SEC code">
        <span className="font-mono">{t.transaction_code ?? '—'}</span>
        <span className="text-muted"> · {titleCase(t.transaction_direction)}</span>
      </Row>
      <Row label="Transaction date">{fmtDate(t.transaction_date)}</Row>
      <Row label="Filed (accepted)">{fmtTimestamp(t.filing_timestamp)}</Row>
      <Row label="Disclosure">{disclosureNote(t)}</Row>
      <Row label="Shares">
        <span className="tabular">{fmtShares(t.shares)}</span>
        {t.security_title ? <span className="text-muted"> {t.security_title}</span> : null}
      </Row>
      <Row label="Price per share">
        <span className="tabular">{fmtPrice(t.price_per_share)}</span>
      </Row>
      <Row label="Transaction value">
        <span className="tabular">{fmtMoney(t.transaction_value)}</span>
      </Row>
      <Row label="Owned after">
        <span className="tabular">{fmtShares(t.shares_owned_after)}</span>
      </Row>
      <Row label="Ownership">
        {t.ownership_type ?? '—'}
        {t.ownership_nature ? <span className="text-muted"> · {t.ownership_nature}</span> : null}
      </Row>
      <Row label="Derivative">
        {t.is_derivative
          ? `Yes${t.underlying_security_title ? ` · ${fmtShares(t.underlying_shares)} ${t.underlying_security_title}` : ''}${t.exercise_price ? ` · exercise price ${fmtPrice(t.exercise_price)}` : ''}`
          : 'No'}
      </Row>
      <Row label="Rule 10b5-1 plan">
        {triState(t.is_10b5_1)}
        {t.is_10b5_1_source ? <span className="text-muted"> (from {t.is_10b5_1_source})</span> : null}
      </Row>
      <Row label="Open market">{triState(t.is_market_transaction)}</Row>
      <Row label="Discretionary">{triState(t.is_discretionary_trade)}</Row>
      <Row label="Data quality">
        <StatusBadge status={t.quality_status} />
      </Row>
      <Row label="Source filing">
        {t.sec_filing_url ? (
          <a
            href={t.sec_filing_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-exercise hover:underline"
          >
            {t.accession_number} <ExternalLink className="size-3" />
          </a>
        ) : (
          t.accession_number
        )}
        <span className="text-muted"> · Form {t.form_type}</span>
      </Row>
    </dl>
  )
}

export function TransactionDetailSheet() {
  const { ticker, selectedId, openTransaction } = useAppState()
  const query = useQuery({
    queryKey: ['transaction', ticker, selectedId],
    queryFn: () => api.transaction(ticker!, selectedId!),
    enabled: !!ticker && !!selectedId,
  })
  const t = query.data?.record

  return (
    <Sheet open={!!selectedId} onOpenChange={(open) => !open && openTransaction(null)}>
      <SheetContent
        title={t ? `${t.insider_name ?? 'Unknown insider'} · ${t.transaction_type}` : 'Transaction'}
        description={t ? `${t.transaction_id} · ${t.source_transaction_id}` : undefined}
      >
        {query.isPending ? (
          <div className="space-y-2 p-5">
            {Array.from({ length: 8 }, (_, i) => (
              <Skeleton key={i} className="h-5" />
            ))}
          </div>
        ) : query.isError ? (
          <ErrorState error={query.error} className="m-5" />
        ) : t ? (
          <>
            <Section title="Transaction">
              <TransactionFacts t={t} />
            </Section>
            {t.quality_flags.length > 0 ? (
              <Section title="Quality checks">
                <ul className="space-y-1.5">
                  {t.quality_flags.map((flag, i) => (
                    <li key={flag} className="text-[13px]">
                      <span className="mr-2 font-mono text-[11px] text-muted">{flag}</span>
                      {t.quality_explanations[i]}
                    </li>
                  ))}
                </ul>
              </Section>
            ) : null}
            <Section title="Classification">
              <p className="text-[13px]">{t.classification_reason}</p>
              <p className="mt-1 text-xs text-muted">Confidence: {titleCase(t.classification_confidence)}</p>
            </Section>
            <Section title="Amendments">
              <p className="text-[13px]">
                {titleCase(t.amendment_status)}
                {t.is_current ? '' : ' · not in the current view'}
              </p>
              {t.amends_accession_number ? (
                <p className="text-xs text-muted">Reconciled against {t.amends_accession_number}</p>
              ) : null}
              {t.superseded_by ? (
                <button
                  type="button"
                  className="mt-1 text-xs text-exercise hover:underline"
                  onClick={() => openTransaction(t.superseded_by)}
                >
                  Replaced by {t.superseded_by}
                </button>
              ) : null}
            </Section>
            {t.footnotes.length > 0 ? (
              <Section title="Footnotes">
                <ul className="space-y-2">
                  {t.footnotes.map((n) => (
                    <li key={n.id} className="text-[13px]">
                      <Badge tone="muted" className="mr-2 font-mono">{n.id}</Badge>
                      {n.text ?? <em className="text-muted">Referenced but missing from the filing.</em>}
                      <div className="mt-0.5 text-[11px] text-muted">on {n.fields.join(', ')}</div>
                    </li>
                  ))}
                </ul>
              </Section>
            ) : null}
            {t.reporting_owner_count > 1 ? (
              <Section title="Reporting owners (joint filing)">
                <ul className="text-[13px]">
                  {t.reporting_owners.map((o) => (
                    <li key={o.cik ?? o.name}>
                      {o.name} <span className="text-muted">CIK {o.cik}</span>
                    </li>
                  ))}
                </ul>
              </Section>
            ) : null}
            {t.related_transaction_ids.length > 0 ? (
              <Section title="Related transactions">
                <div className="flex flex-wrap gap-2">
                  {t.related_transaction_ids.map((id) => (
                    <button
                      key={id}
                      type="button"
                      className="font-mono text-xs text-exercise hover:underline"
                      onClick={() => openTransaction(id)}
                    >
                      {id}
                    </button>
                  ))}
                </div>
              </Section>
            ) : null}
            <Section title={`Cleaning log (${query.data?.cleaning_log.length ?? 0})`}>
              <ul className="space-y-1 text-xs">
                {query.data?.cleaning_log.map((d, i) => (
                  <li key={i}>
                    <span className="text-muted">{d.field ?? d.step}:</span> {d.rule}
                    {d.before !== null || d.after !== null ? (
                      <span className="font-mono text-muted">
                        {' '}
                        “{d.before ?? ''}” → “{d.after ?? ''}”
                      </span>
                    ) : null}
                  </li>
                ))}
              </ul>
            </Section>
            <Section title="Source values">
              <pre className="max-h-72 overflow-auto rounded bg-panel-2 p-3 font-mono text-[11px] leading-relaxed">
                {JSON.stringify(t.source_values, null, 2)}
              </pre>
            </Section>
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  )
}
