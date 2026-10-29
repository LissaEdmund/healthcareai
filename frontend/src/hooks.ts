import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, type Catalog } from "./api";

export interface ApiState<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
  reload: () => void;
  setData: (d: T | null) => void;
}

function toApiError(e: unknown): ApiError {
  if (e instanceof ApiError) return e;
  return new ApiError(0, "CLIENT_ERROR", e instanceof Error ? e.message : String(e));
}

/** Load data from the API; re-runs when `deps` change. Pass `null` to skip. */
export function useApi<T>(fn: (() => Promise<T>) | null, deps: unknown[]): ApiState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState<boolean>(fn !== null);
  const [tick, setTick] = useState(0);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    const f = fnRef.current;
    if (!f) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    f()
      .then((d) => {
        if (!cancelled) {
          setData(d);
          setError(null);
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(toApiError(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, reload, setData };
}

/** Track an async mutation (form submit / button) with its error state. */
export function useMutation() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const run = useCallback(async <R,>(fn: () => Promise<R>): Promise<R | undefined> => {
    setBusy(true);
    setError(null);
    try {
      return await fn();
    } catch (e) {
      setError(toApiError(e));
      return undefined;
    } finally {
      setBusy(false);
    }
  }, []);
  return { busy, error, setError, run };
}

let catalogPromise: Promise<Catalog> | null = null;

/** The coded vocabularies change only with the backend; load once per page session. */
export function useCatalog(): ApiState<Catalog> {
  return useApi(() => {
    if (!catalogPromise) {
      catalogPromise = api.catalog().catch((e) => {
        catalogPromise = null;
        throw e;
      });
    }
    return catalogPromise;
  }, []);
}
