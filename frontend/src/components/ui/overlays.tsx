import * as CheckboxPrimitive from '@radix-ui/react-checkbox'
import * as DialogPrimitive from '@radix-ui/react-dialog'
import * as DropdownPrimitive from '@radix-ui/react-dropdown-menu'
import * as PopoverPrimitive from '@radix-ui/react-popover'
import { Check, X } from 'lucide-react'
import * as React from 'react'

import { cn } from '@/lib/utils'

// Sheet: a panel that slides in from the right (Radix Dialog).
export const Sheet = DialogPrimitive.Root
export const SheetClose = DialogPrimitive.Close

export function SheetContent({
  className,
  children,
  title,
  description,
  ...props
}: React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content> & {
  title: React.ReactNode
  description?: React.ReactNode
}) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-black/50" />
      <DialogPrimitive.Content
        className={cn(
          'fixed inset-y-0 right-0 z-50 flex w-full max-w-xl flex-col border-l border-border bg-panel shadow-2xl focus:outline-none',
          className,
        )}
        {...props}
      >
        <div className="flex items-start justify-between gap-3 border-b border-border px-5 py-3.5">
          <div className="min-w-0">
            <DialogPrimitive.Title className="text-sm font-semibold">{title}</DialogPrimitive.Title>
            {description ? (
              <DialogPrimitive.Description className="mt-0.5 text-xs text-muted">
                {description}
              </DialogPrimitive.Description>
            ) : (
              <DialogPrimitive.Description className="sr-only">Details</DialogPrimitive.Description>
            )}
          </div>
          <DialogPrimitive.Close className="rounded p-1 text-muted hover:bg-accent hover:text-foreground">
            <X className="size-4" />
            <span className="sr-only">Close</span>
          </DialogPrimitive.Close>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  )
}

export const Popover = PopoverPrimitive.Root
export const PopoverTrigger = PopoverPrimitive.Trigger

export function PopoverContent({
  className,
  ...props
}: React.ComponentPropsWithoutRef<typeof PopoverPrimitive.Content>) {
  return (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Content
        sideOffset={6}
        align="start"
        className={cn(
          'z-50 max-h-[70vh] overflow-y-auto rounded-lg border border-border bg-panel p-3 shadow-xl focus:outline-none',
          className,
        )}
        {...props}
      />
    </PopoverPrimitive.Portal>
  )
}

export const DropdownMenu = DropdownPrimitive.Root
export const DropdownMenuTrigger = DropdownPrimitive.Trigger

export function DropdownMenuContent({
  className,
  ...props
}: React.ComponentPropsWithoutRef<typeof DropdownPrimitive.Content>) {
  return (
    <DropdownPrimitive.Portal>
      <DropdownPrimitive.Content
        sideOffset={6}
        align="end"
        className={cn(
          'z-50 max-h-[60vh] min-w-48 overflow-y-auto rounded-lg border border-border bg-panel p-1 shadow-xl',
          className,
        )}
        {...props}
      />
    </DropdownPrimitive.Portal>
  )
}

export function DropdownMenuCheckboxItem({
  className,
  children,
  ...props
}: React.ComponentPropsWithoutRef<typeof DropdownPrimitive.CheckboxItem>) {
  return (
    <DropdownPrimitive.CheckboxItem
      className={cn(
        'relative flex cursor-default select-none items-center rounded py-1.5 pl-7 pr-2 text-[13px] outline-none data-[highlighted]:bg-accent',
        className,
      )}
      onSelect={(e) => e.preventDefault()}
      {...props}
    >
      <span className="absolute left-2 flex size-3.5 items-center justify-center">
        <DropdownPrimitive.ItemIndicator>
          <Check className="size-3.5" />
        </DropdownPrimitive.ItemIndicator>
      </span>
      {children}
    </DropdownPrimitive.CheckboxItem>
  )
}

export function Checkbox({
  className,
  ...props
}: React.ComponentPropsWithoutRef<typeof CheckboxPrimitive.Root>) {
  return (
    <CheckboxPrimitive.Root
      className={cn(
        'peer size-4 shrink-0 rounded border border-border bg-panel-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring data-[state=checked]:border-foreground data-[state=checked]:bg-foreground data-[state=checked]:text-background',
        className,
      )}
      {...props}
    >
      <CheckboxPrimitive.Indicator className="flex items-center justify-center">
        <Check className="size-3" strokeWidth={3} />
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  )
}
