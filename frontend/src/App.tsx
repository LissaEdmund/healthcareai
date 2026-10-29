import type { ReactNode } from "react";
import { Link, Route, Routes } from "react-router-dom";
import type { Permission } from "./api";
import { useAuth } from "./auth";
import { PrototypeBanner } from "./components/Banner";
import { Layout } from "./components/Layout";
import { Loading } from "./components/StateViews";
import { AuditPage } from "./pages/AuditPage";
import { DashboardPage } from "./pages/DashboardPage";
import { EncounterDetailPage } from "./pages/EncounterDetailPage";
import { EncountersPage } from "./pages/EncountersPage";
import { LoginPage } from "./pages/LoginPage";
import { PatientHistoryPage } from "./pages/PatientHistoryPage";
import { QueuePage } from "./pages/QueuePage";
import { ReviewDetailPage } from "./pages/ReviewDetailPage";
import { ReviewsPage } from "./pages/ReviewsPage";
import { WorkflowPage } from "./pages/WorkflowPage";

function Guard({ perm, children }: { perm: Permission; children: ReactNode }) {
  const { can } = useAuth();
  if (!can(perm)) {
    return (
      <div className="error-box" role="alert">
        <strong>Not available for your role</strong>
        <div>This page requires the permission “{perm}”.</div>
        <Link to="/">Back to dashboard</Link>
      </div>
    );
  }
  return <>{children}</>;
}

export function App() {
  const { user, checking } = useAuth();
  return (
    <>
      <PrototypeBanner />
      {checking ? (
        <div className="app-main">
          <Loading label="Checking session…" />
        </div>
      ) : !user ? (
        <LoginPage />
      ) : (
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<DashboardPage />} />
            <Route path="encounters" element={<Guard perm="patient:read_basic"><EncountersPage /></Guard>} />
            <Route path="encounters/:id" element={<Guard perm="patient:read_basic"><EncounterDetailPage /></Guard>} />
            <Route path="patients/:pid/history" element={<Guard perm="patient:read_basic"><PatientHistoryPage /></Guard>} />
            <Route path="workflows/:threadId" element={<Guard perm="triage:run"><WorkflowPage /></Guard>} />
            <Route path="reviews" element={<Guard perm="review:read"><ReviewsPage /></Guard>} />
            <Route path="reviews/:id" element={<Guard perm="review:read"><ReviewDetailPage /></Guard>} />
            <Route path="queue" element={<Guard perm="queue:read"><QueuePage /></Guard>} />
            <Route path="audit" element={<Guard perm="audit:read"><AuditPage /></Guard>} />
            <Route
              path="*"
              element={
                <div className="state state-empty">
                  <h1>Page not found</h1>
                  <Link to="/">Back to dashboard</Link>
                </div>
              }
            />
          </Route>
        </Routes>
      )}
    </>
  );
}
