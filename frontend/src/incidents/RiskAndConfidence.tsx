import type { Incident } from "../api/contracts";
import { RISK_LEVEL_LABELS } from "../labels";

/** Confidence as a whole percentage, or null. */
const confidenceText = (confidence: number | null | undefined) =>
  confidence === null || confidence === undefined ? null : `${Math.round(confidence * 100)}%`;

/**
 * Risk score, risk level and confidence in three separate boxes, because each means something
 * different: the score and level are C3's deterministic risk; the confidence is the AI analysis'.
 * Nothing is computed here.
 */
export function RiskAndConfidence({ incident, confidence }: { incident: Incident; confidence: number | null | undefined }) {
  const shownConfidence = confidenceText(confidence);
  return (
    <div className="metric-row" role="group" aria-label="Risk and confidence">
      <div className="metric">
        <span className="metric__label">Risk score</span>
        <span className="metric__value">{incident.risk ? `${incident.risk.score} / 100` : "Not scored"}</span>
        <span className="metric__note">Computed by the risk engine (C3)</span>
      </div>
      <div className="metric">
        <span className="metric__label">Risk level</span>
        <span className="metric__value">{incident.risk ? RISK_LEVEL_LABELS[incident.risk.level] : "Not scored"}</span>
        <span className="metric__note">From the score and the configured thresholds</span>
      </div>
      <div className="metric">
        <span className="metric__label">Confidence</span>
        <span className="metric__value">{shownConfidence ?? "Not available"}</span>
        <span className="metric__note">
          {shownConfidence === null
            ? "Set when the AI analysis succeeds"
            : (confidence ?? 0) < 0.75
              ? "Below 0.75: no automatic response window"
              : "How sure the AI analysis is"}
        </span>
      </div>
    </div>
  );
}
