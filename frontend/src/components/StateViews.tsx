import type { ReactNode } from "react";
import type { ApiError } from "../api";

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <p className="state state-loading" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" /> {label}
    </p>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="state state-empty">{children}</p>;
}

export function ErrorBox({ error, title, onRetry }: { error: ApiError | Error | null; title?: string; onRetry?: () => void }) {
  if (!error) return null;
  const status = "status" in error ? (error as ApiError).status : 0;
  const code = "code" in error ? (error as ApiError).code : undefined;
  let hint = "";
  if (status === 403) hint = "Your role does not have permission for this.";
  else if (status === 404) hint = "The requested record was not found.";
  else if (status === 409) hint = "The record is in a state that does not allow this action.";
  else if (status === 503) hint = "A backend service is unavailable.";
  return (
    <div className="error-box" role="alert">
      <strong>{title ?? "Error"}</strong>
      {code ? <span className="error-code"> ({status ? `${status} ` : ""}{code})</span> : null}
      <div>{error.message}</div>
      {hint ? <div className="muted">{hint}</div> : null}
      {onRetry ? (
        <button type="button" className="btn btn-small" onClick={onRetry}>
          Try again
        </button>
      ) : null}
    </div>
  );
}

/** Wraps the three states for a data view. */
export function DataState<T>({
  state,
  label,
  isEmpty,
  empty,
  children,
}: {
  state: { data: T | null; error: ApiError | null; loading: boolean; reload: () => void };
  label?: string;
  isEmpty?: (d: T) => boolean;
  empty?: ReactNode;
  children: (d: T) => ReactNode;
}) {
  if (state.error && !state.data) return <ErrorBox error={state.error} title={`Could not load ${label ?? "data"}`} onRetry={state.reload} />;
  if (state.loading && !state.data) return <Loading label={`Loading ${label ?? "data"}…`} />;
  if (!state.data) return <Empty>No data.</Empty>;
  if (isEmpty && isEmpty(state.data)) return <Empty>{empty ?? "Nothing to show."}</Empty>;
  return (
    <>
      {state.error ? <ErrorBox error={state.error} title={`Could not refresh ${label ?? "data"}`} onRetry={state.reload} /> : null}
      {children(state.data)}
    </>
  );
}
