import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { DataState, Empty } from "../components/StateViews";
import { fmtTime } from "../format";
import { useApi } from "../hooks";

export function QueuePage() {
  const { can } = useAuth();
  const state = useApi(() => api.queue(), []);
  return (
    <>
      <div className="page-head">
        <h1>Synthetic queue</h1>
        <button type="button" className="btn btn-small" onClick={state.reload} disabled={state.loading}>
          {state.loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>
      <DataState state={state} label="synthetic queue">
        {(q) => (
          <>
            <div className="queue-label" role="note">
              {q.label}
            </div>
            <p className="muted">Priorities appear here only after an authorized reviewer approved them and the action was applied.</p>
            {q.entries.length === 0 ? (
              <Empty>The synthetic queue is empty (no open encounters).</Empty>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">#</th>
                      <th scope="col">Priority</th>
                      <th scope="col">Synthetic patient</th>
                      <th scope="col">Encounter</th>
                      <th scope="col">Chief complaint</th>
                      <th scope="col">Arrived</th>
                      <th scope="col">Updated</th>
                      <th scope="col">Set by action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {q.entries.map((e, i) => (
                      <tr key={e.encounter_id}>
                        <td>{i + 1}</td>
                        <td>{e.priority ? <strong className="priority">{e.priority}</strong> : <span className="muted">Not set</span>}</td>
                        <td>
                          {e.given_name} {e.family_name}
                          <div className="mono muted small">{e.patient_id}</div>
                        </td>
                        <td className="mono">
                          {can("patient:read_basic") ? <Link to={`/encounters/${e.encounter_id}`}>{e.encounter_id}</Link> : e.encounter_id}
                        </td>
                        <td>{e.chief_complaint}</td>
                        <td className="nowrap">{fmtTime(e.arrived_at)}</td>
                        <td className="nowrap">{fmtTime(e.updated_at)}</td>
                        <td className="mono">{e.updated_by_action_id ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </DataState>
    </>
  );
}
