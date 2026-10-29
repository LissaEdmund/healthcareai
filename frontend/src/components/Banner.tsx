export const BANNER_TEXT =
  "PROTOTYPE — SYNTHETIC DATA ONLY — NOT FOR CLINICAL USE — no real hospital system is connected";

export function PrototypeBanner() {
  return (
    <div className="prototype-banner" role="note" aria-label="Prototype notice">
      <strong>{BANNER_TEXT}</strong>
    </div>
  );
}
