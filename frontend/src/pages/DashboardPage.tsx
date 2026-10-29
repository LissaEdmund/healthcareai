import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { Badge, StatusBadge } from "../components/Badge";
import { DataState, Empty } from "../components/StateViews";
import { fmtTime } from "../format";
import { useApi } from "../hooks";

const REVIEW_STATUSES = ["PENDING", "APPROVED", "REJECTED", "CLARIFICATION_REQUESTED", "EXECUTED", "EXECUTION_FAILED"];

export function DashboardPage() {
  const { user } = useAuth();
  const state = useApi(() => api.dashboard(), []);

  return (
    <>
      <div className="page-head">
        <h1>Dashboard</h1>
        <button type="button" className="btn btn-small" onClick={state.reload} disabled={state.loading}>
          {state.loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>
      <p className="muted">Signed in as {user?.display_name}.</p>
      <DataState state={state} label="dashboard">
        {(d) => (
          <>
            <div className="tiles">
              {d.encounters ? (
                <Link to="/encounters" className="tile">
                  <span className="tile-label">Open encounters</span>
                  <span className="tile-value">{d.encounters.open}</span>
                  <span className="muted small">{d.encounters.total} total</span>
                </Link>
              ) : null}
              {d.urgent_pending !== undefined ? (
                <Link to="/reviews?status=PENDING" className={`tile ${d.urgent_pending > 0 ? "tile-danger" : ""}`}>
                  <span className="tile-label">Urgent reviews pending</span>
                  <span className="tile-value">{d.urgent_pending}</span>
                  <span className="small">{d.urgent_pending > 0 ? "⚠ Escalation criterion met — review now" : "None"}</span>
                </Link>
              ) : null}
              <div className="tile">
                <span className="tile-label">Local model</span>
                <span className="tile-value-sm">
                  {d.model.available ? <Badge tone="ok">✓ Available</Badge> : <Badge tone="warn">! Unavailable</Badge>}
                </span>
                <span className="muted small">
                  {d.model.model ? `${d.model.model}: ` : ""}
                  {d.model.detail}
                </span>
              </div>
              <div className="tile">
                <span className="tile-label">Demo mode</span>
                <span className="tile-value-sm">
                  {d.demo_mode ? <Badge tone="synthetic">ON — synthetic demo protocol allowed</Badge> : <Badge>OFF</Badge>}
                </span>
              </div>
            </div>

            {d.reviews ? (
              <section className="card" aria-label="Reviews by status">
                <h2>Nurse reviews by status</h2>
                <ul className="status-counts">
                  {REVIEW_STATUSES.map((s) => (
                    <li key={s}>
                      <Link to={`/reviews?status=${s}`}>
                        <StatusBadge status={s} /> <strong>{d.reviews?.[s] ?? 0}</strong>
                      </Link>
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}

            {d.recent_events ? (
              <section className="card" aria-label="Recent events">
                <h2>Recent events</h2>
                {d.recent_events.length === 0 ? (
                  <Empty>No events recorded yet.</Empty>
                ) : (
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th scope="col">Time</th>
                          <th scope="col">Event</th>
                          <th scope="col">Actor</th>
                          <th scope="col">Tool</th>
                          <th scope="col">Outcome</th>
                          <th scope="col">Encounter / review</th>
                        </tr>
                      </thead>
                      <tbody>
                        {d.recent_events.map((e, i) => (
                          <tr key={i}>
                            <td className="nowrap">{fmtTime(e.ts)}</td>
                            <td className="mono">{e.event_type}</td>
                            <td>{e.actor_id ?? "—"}</td>
                            <td className="mono">{e.tool_name ?? "—"}</td>
                            <td>
                              <StatusBadge status={e.outcome} />
                            </td>
                            <td className="mono">
                              {e.encounter_id ? <Link to={`/encounters/${e.encounter_id}`}>{e.encounter_id}</Link> : "—"}
                              {e.review_id ? (
                                <>
                                  {" / "}
                                  <Link to={`/reviews/${e.review_id}`}>{e.review_id}</Link>
                                </>
                              ) : null}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            ) : null}
            <p className="muted small">{d.notice}</p>
          </>
        )}
      </DataState>
    </>
  );
}
