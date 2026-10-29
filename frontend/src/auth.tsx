import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, loadToken, onUnauthorized, setToken, type Permission, type User } from "./api";

interface AuthState {
  user: User | null;
  /** true while an existing session token is being checked on page load */
  checking: boolean;
  /** message shown on the login page (e.g. session expired) */
  notice: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  can: (permission: Permission) => boolean;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState<boolean>(() => loadToken() !== null);
  const [notice, setNotice] = useState<string | null>(null);

  const clear = useCallback((message: string | null) => {
    setToken(null);
    setUser(null);
    setNotice(message);
  }, []);

  useEffect(() => {
    onUnauthorized(() => clear("Your session has ended. Please sign in again."));
    return () => onUnauthorized(null);
  }, [clear]);

  // Restore a session from sessionStorage on reload.
  useEffect(() => {
    if (!loadToken()) return;
    let cancelled = false;
    api
      .me()
      .then((u) => {
        if (!cancelled) setUser(u);
      })
      .catch(() => {
        if (!cancelled) clear(null);
      })
      .finally(() => {
        if (!cancelled) setChecking(false);
      });
    return () => {
      cancelled = true;
    };
  }, [clear]);

  const login = useCallback(async (username: string, password: string) => {
    const res = await api.login(username, password);
    setToken(res.token);
    setNotice(null);
    setUser(res.user);
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } catch {
      // token may already be invalid; clear locally regardless
    }
    clear("You have signed out.");
  }, [clear]);

  const value = useMemo<AuthState>(
    () => ({
      user,
      checking,
      notice,
      login,
      logout,
      can: (p: Permission) => !!user && user.permissions.includes(p),
    }),
    [user, checking, notice, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
