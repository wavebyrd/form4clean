import * as React from 'react'

import { cn } from '@/lib/utils'

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('rounded-lg border border-border bg-panel', className)} {...props} />
}

export function CardHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('flex items-center justify-between gap-2 border-b border-border px-4 py-2.5', className)}
      {...props}
    />
  )
}

export function CardTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h3 className={cn('text-[13px] font-semibold tracking-tight', className)} {...props} />
}

export function CardContent({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('p-4', className)} {...props} />
}

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        'h-8 w-full rounded-md border border-border bg-panel-2 px-2.5 text-[13px] placeholder:text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50',
        className,
      )}
      {...props}
    />
  ),
)
Input.displayName = 'Input'

export const NativeSelect = React.forwardRef<
  HTMLSelectElement,
  React.SelectHTMLAttributes<HTMLSelectElement>
>(({ className, children, ...props }, ref) => (
  <select
    ref={ref}
    className={cn(
      'h-8 w-full rounded-md border border-border bg-panel-2 px-2 text-[13px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
      className,
    )}
    {...props}
  >
    {children}
  </select>
))
NativeSelect.displayName = 'NativeSelect'

export function Label({ className, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label
      className={cn('mb-1 block text-[11px] font-medium uppercase tracking-wide text-muted', className)}
      {...props}
    />
  )
}

const BADGE_TONES = {
  neutral: 'bg-accent text-foreground',
  buy: 'bg-buy/15 text-buy',
  sell: 'bg-sell/15 text-sell',
  warn: 'bg-warn/15 text-warn',
  exercise: 'bg-exercise/15 text-exercise',
  comp: 'bg-comp/15 text-comp',
  other: 'bg-other/15 text-other',
  muted: 'bg-transparent text-muted border border-border',
} as const

export type BadgeTone = keyof typeof BADGE_TONES

export function Badge({
  tone = 'neutral',
  className,
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { tone?: BadgeTone }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 whitespace-nowrap rounded px-1.5 py-0.5 text-[11px] font-medium',
        BADGE_TONES[tone],
        className,
      )}
      {...props}
    />
  )
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded-md bg-accent', className)} />
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={cn(
        'inline-block size-4 animate-spin rounded-full border-2 border-muted border-t-transparent',
        className,
      )}
    />
  )
}
