import type { ReactNode } from "react";

/** La tarjeta que envuelve cada visual.
 *
 * `dragHandle` marca la zona por la que se arrastra: solo la cabecera. Si toda
 * la tarjeta fuese asa, no se podria interactuar con el grafico. */
export function Card({
  title,
  subtitle,
  actions,
  children,
  footer,
  dragHandle = false,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  dragHandle?: boolean;
}) {
  return (
    <div className="flex h-full flex-col overflow-hidden rounded-card border border-bone-300 bg-bone-50 shadow-paper">
      <header
        className={`flex items-start justify-between gap-2 border-b border-bone-200 px-3 py-2 ${
          dragHandle ? "card-drag-handle cursor-grab active:cursor-grabbing" : ""
        }`}
      >
        <div className="min-w-0">
          <h3 className="truncate text-sm font-medium text-ink-900">{title}</h3>
          {subtitle && <p className="truncate text-xs text-ink-400">{subtitle}</p>}
        </div>
        {actions && <div className="flex shrink-0 items-center gap-1">{actions}</div>}
      </header>
      <div className="min-h-0 flex-1 p-2">{children}</div>
      {footer}
    </div>
  );
}

export function IconButton({
  label,
  onClick,
  danger = false,
  children,
}: {
  label: string;
  onClick: () => void;
  danger?: boolean;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      onClick={onClick}
      className={`rounded p-1 text-ink-300 transition-colors hover:bg-bone-200 ${
        danger ? "hover:text-alert" : "hover:text-ink-700"
      }`}
    >
      {children}
    </button>
  );
}
