/* GENERATED from contracts/schemas by scripts/gen-contract-types.mjs. Do not edit by hand. */

/**
 * How strongly a finding is supported (FR-15).
 *
 * This interface was referenced by `AnalysisReport`'s JSON-Schema
 * via the `definition` "FindingCategory".
 */
export type FindingCategory = "evidence_supported" | "likely_interpretation" | "hypothesis";

/**
 * The AI's structured result for one incident. null in a section means not determined.
 */
export interface AnalysisReport {
  /**
   * Suspected attack type or category; null = not determined.
   */
  attack_type?: string | null;
  /**
   * Computed by the analysis component from grounding and evidence completeness, not by the model (OD-16). The mock sets 0.0.
   */
  confidence: number;
  /**
   * The EvidencePackage the report came from.
   */
  evidence_package_id: string;
  /**
   * Suspicious behaviour with evidence; empty when there is no evidence.
   */
  findings: Finding[];
  /**
   * When the report was produced, UTC.
   */
  generated_at: string;
  /**
   * Analyzer backend.
   */
  generated_by: "mock" | "hpc" | "local";
  /**
   * Possible impact; null = not determined.
   */
  impact?: string | null;
  /**
   * ID of the analysed incident.
   */
  incident_id: string;
  /**
   * Pinned model name; null for the mock.
   */
  model_id?: string | null;
  /**
   * The model's own rating. Stored, never used for the 0.75 gate (OD-16).
   */
  model_self_rating?: number | null;
  /**
   * Prompt version; null for the mock.
   */
  prompt_version?: string | null;
  /**
   * Free text for the analyst. Never drives an action (C-10).
   */
  recommendations: string[];
  /**
   * Unique report ID.
   */
  report_id: string;
  /**
   * Explains the deterministic score; the report has no score (FR-19). null = not determined.
   */
  risk_justification?: string | null;
  /**
   * Contract version.
   */
  schema_version?: "1.0";
  /**
   * Possible sequence of events; null = not determined.
   */
  sequence?: [SequenceStep, ...SequenceStep[]] | null;
  /**
   * Concise summary (FR-14).
   */
  summary: string;
  /**
   * Uncertainty and limitations (FR-15).
   */
  uncertainty: string;
  /**
   * Weaknesses, only when the evidence supports them; null = not determined.
   */
  weaknesses?: [string, ...string[]] | null;
}
/**
 * One suspicious behaviour with its evidence (FR-14, FR-15).
 *
 * This interface was referenced by `AnalysisReport`'s JSON-Schema
 * via the `definition` "Finding".
 */
export interface Finding {
  category: FindingCategory;
  /**
   * Evidence event IDs. At least one for evidence_supported (FR-15).
   */
  cited_event_ids: string[];
  /**
   * The finding.
   */
  statement: string;
}
/**
 * One step of the possible sequence of events.
 *
 * This interface was referenced by `AnalysisReport`'s JSON-Schema
 * via the `definition` "SequenceStep".
 */
export interface SequenceStep {
  /**
   * Evidence event IDs that support the step.
   *
   * @minItems 1
   */
  cited_event_ids: [string, ...string[]];
  /**
   * What happened in this step.
   */
  description: string;
  /**
   * Position in the sequence: 1, 2, 3, ... with no gaps.
   */
  order: number;
}
