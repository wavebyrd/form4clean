import { AlertTriangle, Inbox } from 'lucide-react'
import type * as React from 'react'

import { Badge, type BadgeTone, Card } from '@/components/ui/primitives'
import { fmtCount } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Category, QualityStatus } from '@/types/api'

const STATUS_TONE: Record<QualityStatus, BadgeTone> = {
  VALID: 'buy',
  WARNING: 'warn',
  REVIEW_REQUIRED: 'other',
  INVALID: 'sell',
}

const STATUS_LABEL: Record<QualityStatus, string> = {
  VALID: 'Valid',
  WARNING: 'Warning',
  REVIEW_REQUIRED: 'Review',
  INVALID: 'Invalid',
}

export function StatusBadge({ status }: { status: QualityStatus }) {
  return <Badge tone={STATUS_TONE[status]}>{STATUS_LABEL[status]}</Badge>
}

const CATEGORY_TONE: Record<Category, BadgeTone> = {
  'Market Purchase': 'buy',
  'Market Sale': 'sell',
  'Derivative Exercise': 'exercise',
  Conversion: 'exercise',
  'Equity Compensation': 'comp',
  'Tax-Related': 'other',
  'Gift or Transfer': 'other',
  Other: 'other',
  Unknown: 'muted',
}

export function CategoryBadge({ category }: { category: Category }) {
  return <Badge tone={CATEGORY_TONE[category]}>{category}</Badge>
}

export function SeverityBadge({ severity }: { severity: string }) {
  const tone: BadgeTone =
    severity === 'INVALID' ? 'sell' : severity === 'REVIEW_REQUIRED' ? 'other' : severity === 'WARNING' ? 'warn' : 'muted'
  return (
    <Badge tone={tone} className="justify-self-start">
      {severity.replace('_', ' ').toLowerCase()}
    </Badge>
  )
}

export function EmptyState({
  title,
  children,
  icon,
  className,
}: {
  title: string
  children?: React.ReactNode
  icon?: React.ReactNode
  className?: string
}) {
  return (
    <div className={cn('flex flex-col items-center justify-center gap-2 px-6 py-14 text-center', className)}>
      <div className="text-muted">{icon ?? <Inbox className="size-6" />}</div>
      <div className="text-sm font-medium">{title}</div>
      {children ? <div className="max-w-md text-[13px] text-muted">{children}</div> : null}
    </div>
  )
}

export function ErrorState({ error, className }: { error: unknown; className?: string }) {
  const message = error instanceof Error ? error.message : String(error)
  return (
    <div
      role="alert"
      className={cn(
        'flex items-start gap-2 rounded-md border border-sell/40 bg-sell/10 px-3 py-2 text-[13px]',
        className,
      )}
    >
      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-sell" />
      <span>{message}</span>
    </div>
  )
}

export function Kpi({
  label,
  value,
  sub,
  tone,
}: {
  label: string
  value: React.ReactNode
  sub?: React.ReactNode
  tone?: 'buy' | 'sell' | 'warn'
}) {
  return (
    <Card className="px-4 py-3">
      <div className="text-[11px] font-medium uppercase tracking-wide text-muted">{label}</div>
      <div
        className={cn(
          'tabular mt-1 text-xl font-semibold',
          tone === 'buy' && 'text-buy',
          tone === 'sell' && 'text-sell',
          tone === 'warn' && 'text-warn',
        )}
      >
        {value}
      </div>
      {sub ? <div className="mt-0.5 text-xs text-muted">{sub}</div> : null}
    </Card>
  )
}

export function StatusBar({ distribution }: { distribution: Record<string, number> }) {
  const total = Object.values(distribution).reduce((a, b) => a + b, 0)
  const parts: { key: QualityStatus; cls: string }[] = [
    { key: 'VALID', cls: 'bg-buy' },
    { key: 'WARNING', cls: 'bg-warn' },
    { key: 'REVIEW_REQUIRED', cls: 'bg-other' },
    { key: 'INVALID', cls: 'bg-sell' },
  ]
  return (
    <div>
      <div className="flex h-2 overflow-hidden rounded-full bg-accent">
        {total > 0 &&
          parts.map((p) =>
            distribution[p.key] ? (
              <div
                key={p.key}
                className={p.cls}
                style={{ width: `${(100 * distribution[p.key]) / total}%` }}
                title={`${p.key}: ${distribution[p.key]}`}
              />
            ) : null,
          )}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
        {parts.map((p) => (
          <span key={p.key} className="inline-flex items-center gap-1.5">
            <span className={cn('size-2 rounded-full', p.cls)} />
            {STATUS_LABEL[p.key]} <span className="tabular text-foreground">{fmtCount(distribution[p.key] ?? 0)}</span>
          </span>
        ))}
      </div>
    </div>
  )
}
