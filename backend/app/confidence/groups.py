"""Evidence groups for the LLM opinion (risk-v1 step 5, design 9A.2 step 3).

A group is what the risk score keeps one value for: the flows of one claimed technique from one
source-side entity (correlation/risk.py groups by (technique, entity)). The LLM is asked once
per group whether the flows look like that technique. This module turns a group into a short,
masked description the prompt can carry, from either of two sources:

- `group_from_events`: the NetFlow v3 events of a stored incident (used by the risk step);
- `build_groups`: the calibration or test split of a NetFlow v3 CSV (used to fit and check
  Platt scaling, app.confidence.llm_calibrate). Groups there are (time block, class, source IP),
  in the blocks of the wanted split only (features.split_of_block), so the LLM is calibrated
  on the same blocks as the classifier and never on its training blocks.

Negative groups. Every group the risk score sees is flagged by the dataset, so the LLM must
also see groups where the claim is wrong, or it can only learn to say yes. A negative group is
the benign flows of one source in one block, given a claimed technique drawn at random (fixed
seed) from the attack classes of the same dataset and split. It is labelled 0 ("the claim is
not a real attack"). The sample holds at most --groups-per-class groups per attack class and
as many benign groups as attack groups; the natural share of attack groups is recorded so the
calibrator can correct its intercept for the 1:1 sample (llm_calibrate.prior_shift).

Masking (C2-D4): no IP address, host or user reaches the description. The source is "SRC",
destinations are DST-1, DST-2, ... in order of first appearance, times are seconds after the
group's first flow. Ports, protocols and flow statistics stay: they are what the LLM judges.
"""

import argparse
import hashlib
import heapq
import json
import statistics
import sys
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from app.confidence import features as F
from app.contracts import Event, LabelStatus
from app.ingest import normalize as norm
from app.ingest.event_types import EventTypes
from app.ingest.nf_v3 import COLUMNS, l7_master

GROUP_FORMAT = "icd-llm-group-v1"
MAX_FLOWS = 50  # flows described per group, as the evidence package cap (MAX_EVIDENCE_EVENTS)
EXAMPLE_FLOWS = 10  # flows listed one by one in the prompt
SEED = 20261126

NUMERIC = (
    "IN_BYTES", "OUT_BYTES", "IN_PKTS", "OUT_PKTS", "FLOW_DURATION_MILLISECONDS",
    "TCP_FLAGS", "MIN_TTL", "MAX_TTL", "RETRANSMITTED_IN_PKTS", "RETRANSMITTED_OUT_PKTS",
    "NUM_PKTS_UP_TO_128_BYTES", "SRC_TO_DST_IAT_AVG", "ICMP_TYPE", "DNS_QUERY_TYPE",
    "FTP_COMMAND_RET_CODE", "TCP_WIN_MAX_IN",
)  # fmt: skip
TCP_FLAG_NAMES = ((1, "FIN"), (2, "SYN"), (4, "RST"), (8, "PSH"), (16, "ACK"), (32, "URG"),
                  (64, "ECE"), (128, "CWR"))  # fmt: skip


@dataclass(frozen=True)
class Flow:
    """One flow, reduced to what the description uses. dst is the real address (masked later)."""

    start_ms: int
    dst: str | None
    dst_port: int | None
    protocol: str | None
    app: str
    values: dict[str, float] = field(default_factory=dict)


@dataclass
class Group:
    group_id: str
    dataset_id: str
    claimed_technique: str
    flows: list[Flow]
    total_flows: int
    y: int | None = None  # 1 real attack, 0 claim is wrong; None at run time (unknown)
    split: str | None = None
    true_class: str | None = None  # the dataset class of the flows (never shown to the LLM)

    def evidence(self) -> dict[str, Any]:
        return describe(self.claimed_technique, self.flows, self.total_flows)

    def record(self) -> dict[str, Any]:
        """One JSON line of a groups file: masked evidence plus the label for calibration."""
        evidence = self.evidence()
        return {
            "format": GROUP_FORMAT,
            "group_id": self.group_id,
            "dataset_id": self.dataset_id,
            "split": self.split,
            "true_class": self.true_class,
            "y": self.y,
            "evidence": evidence,
            "evidence_sha256": evidence_sha256(evidence),
        }


def evidence_sha256(evidence: dict[str, Any]) -> str:
    text = json.dumps(evidence, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _median(values: list[float]) -> float | None:
    return round(float(statistics.median(values)), 3) if values else None


def _top(counter: Counter, n: int = 5) -> dict[str, int]:
    return {str(key): count for key, count in sorted(counter.items(), key=lambda i: (-i[1],
            str(i[0])))[:n]}  # fmt: skip


def tcp_flag_names(bits: int) -> list[str]:
    return [name for bit, name in TCP_FLAG_NAMES if bits & bit]


def describe(claimed: str, flows: list[Flow], total_flows: int) -> dict[str, Any]:
    """The masked, aggregate description of one group; deterministic for the same flows."""
    flows = sorted(flows, key=lambda f: (f.start_ms, f.dst or "", f.dst_port or -1))[:MAX_FLOWS]
    tokens: dict[str, str] = {}
    for flow in flows:
        if flow.dst is not None and flow.dst not in tokens:
            tokens[flow.dst] = f"DST-{len(tokens) + 1}"
    t0 = flows[0].start_ms if flows else 0

    def column(name: str) -> list[float]:
        return [v for f in flows if (v := f.values.get(name)) is not None]

    flags = 0
    for value in column("TCP_FLAGS"):
        flags |= int(value)
    in_bytes, out_bytes = column("IN_BYTES"), column("OUT_BYTES")
    retrans = [
        (f.values.get("RETRANSMITTED_IN_PKTS") or 0) + (f.values.get("RETRANSMITTED_OUT_PKTS") or 0)
        for f in flows
    ]
    span = (flows[-1].start_ms - t0) / 1000 if flows else 0.0
    examples = [
        {
            "t_seconds": round((f.start_ms - t0) / 1000, 3),
            "to": tokens.get(f.dst or "", None),
            "dst_port": f.dst_port,
            "protocol": f.protocol,
            "application": f.app,
            "in_bytes": f.values.get("IN_BYTES"),
            "out_bytes": f.values.get("OUT_BYTES"),
            "in_pkts": f.values.get("IN_PKTS"),
            "out_pkts": f.values.get("OUT_PKTS"),
            "duration_ms": f.values.get("FLOW_DURATION_MILLISECONDS"),
            "tcp_flags": tcp_flag_names(int(f.values.get("TCP_FLAGS") or 0)),
        }
        for f in flows[:EXAMPLE_FLOWS]
    ]
    return {
        "claimed_technique": claimed,
        "source": "SRC",
        "flows_in_group": total_flows,
        "flows_described": len(flows),
        "time_span_seconds": round(span, 3),
        "distinct_destinations": len(tokens),
        "destination_ports": _top(Counter(f.dst_port for f in flows if f.dst_port is not None)),
        "protocols": _top(Counter(f.protocol for f in flows if f.protocol)),
        "applications": _top(Counter(f.app for f in flows)),
        "tcp_flags_seen": tcp_flag_names(flags),
        "in_bytes": {"total": sum(in_bytes), "median": _median(in_bytes)},
        "out_bytes": {"total": sum(out_bytes), "median": _median(out_bytes)},
        "in_pkts_median": _median(column("IN_PKTS")),
        "out_pkts_median": _median(column("OUT_PKTS")),
        "duration_ms_median": _median(column("FLOW_DURATION_MILLISECONDS")),
        "share_no_reply": round(sum(1 for v in out_bytes if v == 0) / len(out_bytes), 3)
        if out_bytes else None,
        "share_retransmitted": round(sum(1 for v in retrans if v > 0) / len(flows), 3)
        if flows else None,
        "ttl_range": [min(column("MIN_TTL"), default=None), max(column("MAX_TTL"), default=None)],
        "icmp_types": _top(Counter(int(v) for v in column("ICMP_TYPE") if v)),
        "dns_query_types": _top(Counter(int(v) for v in column("DNS_QUERY_TYPE") if v)),
        "ftp_return_codes": _top(Counter(int(v) for v in column("FTP_COMMAND_RET_CODE") if v)),
        "example_flows": examples,
    }  # fmt: skip


# --- from stored events (run time) -------------------------------------------------------


def flow_from_event(event: Event) -> Flow:
    extra = event.extra_fields
    values = {name: v for name in NUMERIC if (v := _number(extra.get(name))) is not None}
    return Flow(
        start_ms=int(event.timestamp.timestamp() * 1000),
        dst=str(event.dst_ip) if event.dst_ip is not None else None,
        dst_port=event.dst_port,
        protocol=event.protocol,
        app=event.event_type,
        values=values,
    )


def group_from_events(
    events: Iterable[Event], technique: str, entity: str, incident_id: str
) -> Group | None:
    """The group of one (technique, entity) of a stored incident, or None if it has no NetFlow
    v3 flagged event (other datasets have no p_llm in risk-v1 yet: design 9A.2 step 6)."""
    from app.correlation.risk import entity_of

    chosen = [
        e
        for e in events
        if e.provenance.dataset_id in F.DATASETS
        and e.label.status == LabelStatus.FLAGGED
        and (e.label.attack_type or "unknown") == technique
        and entity_of(e) == entity
    ]
    if not chosen:
        return None
    key = hashlib.sha256(f"{incident_id}|{technique}|{entity}".encode()).hexdigest()[:16]
    return Group(
        group_id=f"grp-{key}",
        dataset_id=chosen[0].provenance.dataset_id,
        claimed_technique=technique,
        flows=[flow_from_event(e) for e in chosen],
        total_flows=len(chosen),
    )


# --- from a NetFlow v3 CSV (calibration and test groups) ---------------------------------

_KEEP = ("FLOW_START_MILLISECONDS", "IPV4_SRC_ADDR", "IPV4_DST_ADDR", "L4_DST_PORT",
         "PROTOCOL", "L7_PROTO", "Label", "Attack", *NUMERIC)  # fmt: skip


def _rows(path: Path) -> Iterator[dict[str, list]]:
    """Columns of _KEEP as Python lists, per batch (pyarrow, strings)."""
    import pyarrow as pa
    from pyarrow import csv

    reader = csv.open_csv(
        path,
        read_options=csv.ReadOptions(block_size=64 << 20),
        convert_options=csv.ConvertOptions(
            column_types={name: pa.string() for name in COLUMNS}, include_columns=list(_KEEP)
        ),
    )
    for batch in reader:
        yield {name: batch.column(name).to_pylist() for name in _KEEP}


def _key(dataset_id: str, cols: dict[str, list], i: int, block_minutes: int,
         splits: dict[int, str]):  # fmt: skip
    """(split, block, class, source) of row i, or None when the row is unusable."""
    label = (cols["Label"][i] or "").strip()
    start = _number(cols["FLOW_START_MILLISECONDS"][i])
    source = norm.clean(cols["IPV4_SRC_ADDR"][i])
    if label not in ("0", "1") or start is None or source is None:
        return None
    block = F.block_of(int(start), block_minutes)
    if block not in splits:
        splits[block] = F.split_of_block(dataset_id, block)
    return splits[block], block, F.class_of(int(label), cols["Attack"][i]), \
        source  # fmt: skip


def _flow(cols: dict[str, list], i: int, types: EventTypes) -> Flow:
    values = {name: v for name in NUMERIC if (v := _number(cols[name][i])) is not None}
    port = _number(cols["L4_DST_PORT"][i])
    return Flow(
        start_ms=int(float(cols["FLOW_START_MILLISECONDS"][i])),
        dst=norm.clean(cols["IPV4_DST_ADDR"][i]),
        dst_port=int(port) if port is not None and 0 <= port <= 65535 else None,
        protocol=norm.iana_protocol(cols["PROTOCOL"][i]),
        app=types.event_type(l7_master(cols["L7_PROTO"][i])),
        values=values,
    )


def choose_groups(
    counts: Counter, groups_per_class: int, seed: int, code: int
) -> dict[tuple, str | None]:
    """Group keys (block, class, source) to describe, each with its claimed technique.

    At most groups_per_class per attack class; benign groups up to the number of attack groups,
    each with a claim drawn from the attack classes. Sorted first, so the draw is stable."""
    rng = np.random.default_rng([seed, code])
    by_class: dict[str, list[tuple]] = {}
    for key in sorted(counts):
        by_class.setdefault(key[1], []).append(key)
    chosen: dict[tuple, str | None] = {}
    attack_classes = sorted(c for c in by_class if c != F.BENIGN)
    for cls in attack_classes:
        keys = by_class[cls]
        picked = rng.choice(len(keys), size=min(groups_per_class, len(keys)), replace=False)
        for index in sorted(picked):
            chosen[keys[index]] = cls
    benign = by_class.get(F.BENIGN, [])
    if benign and attack_classes:
        n = min(len(chosen), len(benign))
        picked = rng.choice(len(benign), size=n, replace=False)
        claims = rng.integers(0, len(attack_classes), size=n)
        for index, claim in zip(sorted(picked), claims, strict=True):
            chosen[benign[index]] = attack_classes[int(claim)]
    return chosen


def build_groups(
    dataset_id: str, path: Path, split: str, groups_per_class: int = 150, code: int = 0,
    block_minutes: int = F.BLOCK_MINUTES,
) -> tuple[list[Group], dict[str, Any]]:  # fmt: skip
    """Two passes: count groups of the split, then keep the earliest MAX_FLOWS flows of the
    chosen ones. Returns the groups and counts for the manifest (no row values)."""
    if dataset_id not in F.DATASETS:
        raise SystemExit(f"error: {dataset_id} is not one of {', '.join(F.DATASETS)}")
    if split not in ("calibration", "test"):
        raise SystemExit("error: groups are built for the calibration or the test split only")
    counts: Counter = Counter()
    splits: dict[int, str] = {}
    for cols in _rows(path):
        for i in range(len(cols["Label"])):
            key = _key(dataset_id, cols, i, block_minutes, splits)
            if key is not None and key[0] == split:
                counts[key[1:]] += 1
    chosen = choose_groups(counts, groups_per_class, SEED, code)
    types = EventTypes(dataset_id)
    kept: dict[tuple, list] = {key: [] for key in chosen}  # heaps of (-start, n, Flow)
    serial = 0
    for cols in _rows(path):
        for i in range(len(cols["Label"])):
            key = _key(dataset_id, cols, i, block_minutes, splits)
            if key is None or key[0] != split or key[1:] not in kept:
                continue
            flow = _flow(cols, i, types)
            heap = kept[key[1:]]
            serial += 1
            item = (-flow.start_ms, -serial, flow)  # earliest MAX_FLOWS stay; ties: file order
            if len(heap) < MAX_FLOWS:
                heapq.heappush(heap, item)
            elif item > heap[0]:
                heapq.heapreplace(heap, item)
    groups = []
    for key, claim in chosen.items():
        block, cls, source = key
        digest = hashlib.sha256(f"{dataset_id}|{block}|{cls}|{source}".encode()).hexdigest()
        groups.append(
            Group(
                group_id=f"{dataset_id}:{split}:{digest[:16]}",
                dataset_id=dataset_id,
                claimed_technique=claim or cls,
                flows=[item[2] for item in kept[key]],
                total_flows=counts[key],
                y=0 if cls == F.BENIGN else 1,
                split=split,
                true_class=cls,
            )
        )
    groups.sort(key=lambda g: g.group_id)
    attack_groups = sum(1 for k in counts if k[1] != F.BENIGN)
    info = {
        "groups_in_split": len(counts),
        "attack_groups_in_split": attack_groups,
        "natural_attack_share": attack_groups / len(counts) if counts else None,
        "groups_chosen": len(groups),
        "attack_groups_chosen": sum(g.y for g in groups),
        "chosen_by_class": dict(sorted(Counter(g.true_class for g in groups).items())),
    }
    return groups, info


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--input", action="append", required=True, metavar="DATASET_ID=PATH")
    parser.add_argument("--split", choices=("calibration", "test"), required=True)
    parser.add_argument("--out", type=Path, required=True, help="groups file (.jsonl)")
    parser.add_argument("--groups-per-class", type=int, default=150)
    parser.add_argument("--block-minutes", type=int, default=F.BLOCK_MINUTES)
    args = parser.parse_args(argv)
    inputs = dict(item.partition("=")[::2] for item in args.input)
    manifest: dict[str, Any] = {"format": GROUP_FORMAT, "split": args.split,
                                "groups_per_class": args.groups_per_class, "seed": SEED,
                                "datasets": {}}  # fmt: skip
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as out:
        for code, (dataset_id, path) in enumerate(sorted(inputs.items())):
            if not Path(path).is_file():
                print(f"error: {path} is not a file", file=sys.stderr)
                return 2
            groups, info = build_groups(
                dataset_id.strip(), Path(path), args.split, args.groups_per_class, code,
                args.block_minutes,
            )  # fmt: skip
            for group in groups:
                out.write(json.dumps(group.record(), sort_keys=True) + "\n")
            manifest["datasets"][dataset_id] = {"file": Path(path).name, **info}
            print(f"{dataset_id}: {info['groups_chosen']} groups "
                  f"({info['attack_groups_chosen']} attack)")  # fmt: skip
    manifest_path = args.out.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
