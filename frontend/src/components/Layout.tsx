import { useEffect, useRef } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import type { Permission } from "../api";
import { useAuth } from "../auth";

interface NavItem {
  to: string;
  label: string;
  /** shown if the user holds any of these permissions (empty = always) */
  any: Permission[];
}

export const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Dashboard", any: [] },
  { to: "/encounters", label: "Encounters", any: ["patient:read_basic"] },
  { to: "/reviews", label: "Review queue", any: ["review:read"] },
  { to: "/queue", label: "Synthetic queue", any: ["queue:read"] },
  { to: "/audit", label: "Audit log", any: ["audit:read"] },
];

export function Layout() {
  const { user, logout, can } = useAuth();
  const location = useLocation();
  const mainRef = useRef<HTMLElement>(null);

  // Move focus to the main region on navigation so keyboard and screen-reader users land on new content.
  useEffect(() => {
    mainRef.current?.focus();
  }, [location.pathname]);

  if (!user) return null;
  const items = NAV_ITEMS.filter((n) => n.any.length === 0 || n.any.some((p) => can(p)));

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="app-header">
        <div className="brand">
          HospitalCare AI <span className="brand-tag">prototype</span>
        </div>
        <nav aria-label="Main">
          <ul className="nav-list">
            {items.map((n) => (
              <li key={n.to}>
                <NavLink to={n.to} end={n.to === "/"} className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}>
                  {n.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <div className="user-box">
          <span>
            <strong>{user.display_name}</strong> <span className="muted">({user.role.replace(/_/g, " ")})</span>
          </span>
          <button type="button" className="btn btn-small" onClick={() => void logout()}>
            Sign out
          </button>
        </div>
      </header>
      <main id="main" ref={mainRef} tabIndex={-1} className="app-main">
        <Outlet />
      </main>
      <footer className="app-footer">
        Synthetic data only. Proposals require review and a decision by an authorized nurse or clinician. The queue shown is a synthetic queue
        and is not connected to any hospital system.
      </footer>
    </div>
  );
}
