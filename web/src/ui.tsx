import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type ReactNode,
} from 'react'

/* ---------------- Button ---------------- */

type Variant = 'default' | 'primary' | 'danger' | 'danger-solid' | 'ghost'

export function Button({
  variant = 'default',
  size,
  loading = false,
  block = false,
  iconOnly = false,
  className = '',
  children,
  disabled,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant
  size?: 'sm'
  loading?: boolean
  block?: boolean
  iconOnly?: boolean
}) {
  const classes = [
    'btn',
    variant !== 'default' ? `btn-${variant}` : '',
    size === 'sm' ? 'btn-sm' : '',
    block ? 'btn-block' : '',
    iconOnly ? 'btn-icon' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ')
  return (
    <button
      type="button"
      {...rest}
      className={classes}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
    >
      {loading && <span className="spinner" aria-hidden="true" />}
      {children}
    </button>
  )
}

/* ---------------- Field ---------------- */

export function Field({
  label,
  hint,
  error,
  children,
  id,
  className = '',
  hideLabel = false,
}: {
  label: string
  hint?: ReactNode
  error?: string
  children: (props: {
    id: string
    'aria-describedby': string | undefined
    'aria-invalid': boolean | undefined
  }) => ReactNode
  id?: string
  className?: string
  hideLabel?: boolean
}) {
  const autoId = useId()
  const fieldId = id ?? autoId
  const hintId = hint ? `${fieldId}-hint` : undefined
  const errorId = error ? `${fieldId}-error` : undefined
  const describedBy = [hintId, errorId].filter(Boolean).join(' ') || undefined

  return (
    <div className={`field ${className}`}>
      <label className={hideLabel ? 'sr-only' : 'field-label'} htmlFor={fieldId}>
        {label}
      </label>
      {children({
        id: fieldId,
        'aria-describedby': describedBy,
        'aria-invalid': error ? true : undefined,
      })}
      {hint && !error && (
        <span className="field-hint" id={hintId}>
          {hint}
        </span>
      )}
      {error && (
        <span className="field-error" id={errorId}>
          {error}
        </span>
      )}
    </div>
  )
}

/* ---------------- Toasts ---------------- */

export type ToastTone = 'success' | 'error' | 'info'
type Toast = { id: number; message: string; tone: ToastTone }

const ToastContext = createContext<(message: string, tone?: ToastTone) => void>(
  () => {}
)

export function useToast() {
  return useContext(ToastContext)
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const nextId = useRef(1)

  const dismiss = useCallback((id: number) => {
    setToasts((t) => t.filter((x) => x.id !== id))
  }, [])

  const push = useCallback(
    (message: string, tone: ToastTone = 'info') => {
      const id = nextId.current++
      setToasts((t) => [...t.slice(-2), { id, message, tone }])
      window.setTimeout(() => dismiss(id), tone === 'error' ? 7000 : 4000)
    },
    [dismiss]
  )

  return (
    <ToastContext.Provider value={push}>
      {children}
      {/* Polite, not assertive: a saved note should not interrupt a screen
          reader mid-sentence. Errors still announce because they are new nodes. */}
      <div className="toast-region" role="status" aria-live="polite" aria-atomic="false">
        {toasts.map((t) => (
          <div key={t.id} className="toast" data-tone={t.tone}>
            <span className="toast-message">{t.message}</span>
            <button
              type="button"
              className="btn btn-ghost btn-icon"
              aria-label="Dismiss notification"
              onClick={() => dismiss(t.id)}
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

/* ---------------- Confirm dialog ---------------- */

export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel,
  cancelLabel = 'Cancel',
  tone = 'danger',
  busy = false,
  onConfirm,
  onCancel,
}: {
  open: boolean
  title: string
  children?: ReactNode
  confirmLabel: string
  cancelLabel?: string
  tone?: 'danger' | 'primary'
  busy?: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (open && !el.open) el.showModal()
    if (!open && el.open) el.close()
  }, [open])

  // Escape and backdrop clicks both cancel; the native dialog handles Escape,
  // this handles the backdrop.
  return (
    <dialog
      ref={ref}
      className="confirm"
      onCancel={(e) => {
        e.preventDefault()
        if (!busy) onCancel()
      }}
      onClick={(e) => {
        if (e.target === ref.current && !busy) onCancel()
      }}
      aria-labelledby="confirm-title"
    >
      <h2 id="confirm-title">{title}</h2>
      <div className="stack">{children}</div>
      <div className="dialog-actions">
        <Button onClick={onCancel} disabled={busy}>
          {cancelLabel}
        </Button>
        <Button
          variant={tone === 'danger' ? 'danger-solid' : 'primary'}
          onClick={onConfirm}
          loading={busy}
          autoFocus
        >
          {confirmLabel}
        </Button>
      </div>
    </dialog>
  )
}

/* ---------------- Empty state ---------------- */

export function EmptyState({
  glyph,
  title,
  children,
  action,
}: {
  glyph: string
  title: string
  children?: ReactNode
  action?: ReactNode
}) {
  return (
    <div className="empty-state">
      <span className="empty-glyph" aria-hidden="true">
        {glyph}
      </span>
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {action}
    </div>
  )
}

/* ---------------- Alert ---------------- */

export function Alert({
  tone = 'info',
  children,
}: {
  tone?: 'info' | 'error' | 'warn' | 'success'
  children: ReactNode
}) {
  return (
    <div className={`alert alert-${tone}`} role={tone === 'error' ? 'alert' : undefined}>
      <span>{children}</span>
    </div>
  )
}

/* ---------------- Status pill ---------------- */

export const STATUSES = [
  'interested',
  'applied',
  'interview',
  'offer',
  'rejected',
  'closed',
] as const
export type JobStatus = (typeof STATUSES)[number]

export const STATUS_LABELS: Record<JobStatus, string> = {
  interested: 'Interested',
  applied: 'Applied',
  interview: 'Interview',
  offer: 'Offer',
  rejected: 'Rejected',
  closed: 'Closed',
}

export function StatusPill({ status }: { status: JobStatus }) {
  return (
    <span className={`pill pill-${status}`}>{STATUS_LABELS[status] ?? status}</span>
  )
}

/* ---------------- Loading ---------------- */

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="loading-page">
      <span className="spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  )
}

/* ---------------- Hooks ---------------- */

/** Debounces a value; used for search so typing does not refilter per keystroke. */
export function useDebounced<T>(value: T, ms = 150): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = window.setTimeout(() => setV(value), ms)
    return () => window.clearTimeout(t)
  }, [value, ms])
  return v
}

export function useStableCallback<T extends (...args: never[]) => unknown>(fn: T): T {
  const ref = useRef(fn)
  useEffect(() => {
    ref.current = fn
  })
  return useMemo(() => ((...args: never[]) => ref.current(...args)) as T, [])
}
