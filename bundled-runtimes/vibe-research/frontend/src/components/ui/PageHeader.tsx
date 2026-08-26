import { type ReactNode } from "react";

interface Props {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}

export function PageHeader({ title, subtitle, actions }: Props) {
  const embedded = window.parent !== window;
  if (embedded && !actions) return null;
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      {!embedded ? <div data-mod-page-title>
        <h1 className="text-2xl font-extrabold tracking-tight text-glow">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>}
      </div> : null}
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
