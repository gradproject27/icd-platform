import type { RiskLevel } from "../api/contracts";
import { RISK_LEVEL_LABELS } from "../labels";

/** An incident's or an entity's risk as the API gives it; null or undefined when not scored. */
type Risk = { level: RiskLevel; score: number } | null | undefined;

/**
 * The risk as a chip: "High 74", text first (wireframes section 5). The shape and colour are extra
 * (triangle, half circle, dot, ring) so the level reads without colour. The score and level come
 * from the risk engine as given; nothing is computed here.
 */
export function RiskChip({ risk }: { risk: Risk }) {
  const level = risk?.level ?? "none";
  return (
    <span className={`chip chip--risk chip--${level}`}>
      <RiskShape level={level} />
      {risk ? `${RISK_LEVEL_LABELS[risk.level]} ${risk.score}` : "Not scored"}
    </span>
  );
}

/** The level's shape alone (decorative), for legends and charts next to a text label. */
export function RiskShape({ level }: { level: RiskLevel | "none" }) {
  return (
    <svg className="chip__shape" viewBox="0 0 10 10" aria-hidden="true" focusable="false">
      {level === "high" && <path d="M5 1 9.4 9H.6z" fill="currentColor" />}
      {level === "medium" && (
        <>
          <circle cx="5" cy="5" r="3.9" fill="none" stroke="currentColor" strokeWidth="1.2" />
          <path d="M5 1.1a3.9 3.9 0 0 0 0 7.8z" fill="currentColor" />
        </>
      )}
      {level === "low" && <circle cx="5" cy="5" r="2.6" fill="currentColor" />}
      {level === "none" && <circle cx="5" cy="5" r="3.4" fill="none" stroke="currentColor" strokeWidth="1.2" />}
    </svg>
  );
}
