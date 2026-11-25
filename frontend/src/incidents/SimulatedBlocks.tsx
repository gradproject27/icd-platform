import { useEffect, useState } from "react";
import { getContainments } from "../api/incidents";
import type { SimulatedContainment } from "../api/proposed";
import { formatLocalDateTime } from "../countdown/clock";

// Timed simulated containment (P2): a simulated IP block of S2 ends on its own (containment.toml,
// GET /incidents/{id}/containments). The server holds the planned end and reverts the block; this
// only shows it. Nothing real is blocked or unblocked.

/** While a block is active, read again this often so the page shows when it ended. */
export const BLOCKS_POLL_MS = 30_000;

function ordinal(offence: number): string {
  return offence === 1 ? "first block of this IP" : `repeat ${offence} of this IP`;
}

function BlockLine({ block }: { block: SimulatedContainment }) {
  const badge = <span className="simulated-badge">[SIMULATED]</span>;
  const extended = block.extended > 0 ? `, extended ${block.extended}×` : "";
  if (block.status === "reverted") {
    return (
      <li>
        Simulated IP block on <strong>{block.target}</strong> ended at {formatLocalDateTime(block.reverted_at ?? block.ends_at)}{" "}
        ({ordinal(block.offence)}{extended}). {badge}
      </li>
    );
  }
  return (
    <li>
      Simulated IP block on <strong>{block.target}</strong> until {formatLocalDateTime(block.ends_at)}, then it ends on
      its own ({ordinal(block.offence)}{extended}). {badge}
    </li>
  );
}

/**
 * The incident's simulated IP blocks with their planned end. Shows nothing when there is none or
 * the server cannot say (an older API): it never hides the decision. `refreshKey` reads again when
 * the decision or the system's outcome changes.
 */
export function SimulatedBlocks({ incidentId, refreshKey }: { incidentId: string; refreshKey: string }) {
  const [blocks, setBlocks] = useState<SimulatedContainment[]>([]);
  const anyActive = blocks.some((block) => block.status === "active");

  // Read once for the incident, and again when the decision or the system's outcome changes.
  useEffect(() => {
    const controller = new AbortController();
    getContainments(incidentId, controller.signal).then(
      (list) => setBlocks(list.items),
      () => undefined,
    );
    return () => controller.abort();
  }, [incidentId, refreshKey]);

  // While a block is active, read again now and then; stop once none is active.
  useEffect(() => {
    if (!anyActive) return;
    const controller = new AbortController();
    const timer = setInterval(() => {
      getContainments(incidentId, controller.signal).then(
        (list) => setBlocks(list.items),
        () => undefined,
      );
    }, BLOCKS_POLL_MS);
    return () => {
      clearInterval(timer);
      controller.abort();
    };
  }, [incidentId, anyActive]);

  if (blocks.length === 0) return null;
  return (
    <section className="box" aria-labelledby="blocks-heading">
      <h2 id="blocks-heading">Simulated IP blocks</h2>
      <ul>
        {blocks.map((block) => (
          <BlockLine key={block.containment_id} block={block} />
        ))}
      </ul>
      <p className="muted">
        A simulated IP block ends on its own at its planned end ({blocks[0]!.config_version}); a repeat of the same IP
        lasts longer. Host isolation never ends on its own: only an analyst releases it.
      </p>
    </section>
  );
}
