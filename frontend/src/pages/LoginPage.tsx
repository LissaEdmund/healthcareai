import { useState, type FormEvent } from "react";
import { ApiError } from "../api";
import { useAuth } from "../auth";

export function LoginPage() {
  const { login, notice } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username.trim(), password);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) setError("Invalid username or password.");
      else setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main id="main" className="login-page">
      <div className="card login-card">
        <h1>HospitalCare AI</h1>
        <p className="muted">
          Outpatient triage workflow assistant — prototype. All patients are synthetic. Every proposal requires review and a decision by an
          authorized nurse or clinician.
        </p>
        {notice ? (
          <p className="notice" role="status">
            {notice}
          </p>
        ) : null}
        <form onSubmit={submit} noValidate>
          <div className="field">
            <label htmlFor="login-username">Username</label>
            <input
              id="login-username"
              name="username"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="login-password">Password</label>
            <input
              id="login-password"
              name="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          {error ? (
            <div className="error-box" role="alert">
              {error}
            </div>
          ) : null}
          <button type="submit" className="btn btn-primary" disabled={busy || !username.trim() || !password}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <p className="muted small">
          Demo accounts: intake.demo, nurse.demo, nurse2.demo, clinician.demo, auditor.demo, admin.demo. The password is set by the
          administrator in the server configuration.
        </p>
      </div>
    </main>
  );
}
