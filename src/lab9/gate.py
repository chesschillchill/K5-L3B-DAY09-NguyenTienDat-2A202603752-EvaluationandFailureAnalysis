"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item
from lab9.graders import GRADERS


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems = []
    pairs_of, tags_of = [], []
    for label, report in (("PR", pr), ("baseline", base)):
        for mid, value in report.get("metrics", {}).items():
            if isinstance(value, (int, float)) and not math.isfinite(value):
                problems.append(f"{label}: non-finite metric {mid}")
        if report.get("evaluator_failures"):
            problems.append(f"{label}: evaluator_failures is non-empty")
        rows = report.get("rows", [])
        manifest = report.get("manifest", {})
        pairs = [(r["item_id"], r["seed"]) for r in rows]
        unique = set(pairs)
        items = {item for item, _ in unique}
        seeds = manifest.get("seeds", sorted({seed for _, seed in unique}))
        # Partial reports used by metric-only callers omit the run manifest.
        count = manifest.get("items", len(items))
        if len(seeds) != len(set(seeds)):
            problems.append(f"{label}: duplicate manifest seeds")
        if len(rows) != count * len(seeds) or len(items) != count:
            problems.append(f"{label}: row/item count differs from manifest item x seed")
        if len(unique) != len(pairs):
            problems.append(f"{label}: duplicate (item_id, seed) rows")
        if unique != {(item, seed) for item in items for seed in seeds}:
            problems.append(f"{label}: incomplete item x seed product")
        if "seeds" in spec and set(seeds) != set(spec["seeds"]):
            problems.append(f"{label}: seeds differ from spec")
        graded = [m["id"] for m in spec["metrics"] if m["id"] in GRADERS
                  and (m.get("grader") or m.get("kind") or any(m["id"] in r for r in rows))]
        for row in rows:
            for mid in graded:
                value = row.get(mid)
                if not isinstance(value, (int, float)) or not math.isfinite(value):
                    problems.append(f"{label}: missing/non-finite grader {mid} at {row['item_id']}@{row['seed']}")
            if "cost" in row and (not isinstance(row["cost"], (int, float)) or not math.isfinite(row["cost"])):
                problems.append(f"{label}: non-finite row cost")
        for m in spec["metrics"]:
            mid = m["id"]
            if m.get("kind") == "safety" and mid in graded:
                values = [r.get(mid) for r in rows]
                if all(isinstance(v, (int, float)) and math.isfinite(v) for v in values):
                    if report.get("metrics", {}).get(mid) != sum(values):
                        problems.append(f"{label}: safety {mid} must count every violation")
        tags = {}
        for row in rows:
            item, slices = row["item_id"], frozenset(row.get("slices") or [])
            if item in tags and tags[item] != slices:
                problems.append(f"{label}: inconsistent slice tags for {item}")
            tags[item] = slices
        pairs_of.append(unique)
        tags_of.append(tags)
    if pairs_of[0] != pairs_of[1]:
        problems.append("PR (item_id, seed) set differs from baseline")
    if tags_of[0] != tags_of[1]:
        problems.append("PR item slice tags differ from baseline")

    if base_spec is not None and spec.get("eval_set_version") == base_spec.get("eval_set_version"):
        for section in ("metrics", "slices"):
            key = (lambda entry: entry["id"]) if section == "metrics" else (lambda entry: (entry["name"], entry["metric"]))
            current = {key(entry): entry for entry in spec.get(section, [])}
            for old in base_spec.get(section, []):
                identity = key(old)
                name = f"ratchet {section}:{identity}"
                new = current.get(identity)
                if new is None:
                    problems.append(f"{name} removed")
                    continue
                if old.get("blocking") and not new.get("blocking"):
                    problems.append(f"{name} blocking removed")
                before = old.get("threshold", {}) if section == "metrics" else old
                after = new.get("threshold", {}) if section == "metrics" else new
                for bound in ("min", "max", "max_increase"):
                    if bound in before:
                        value = after.get(bound)
                        if (not isinstance(value, (int, float)) or not math.isfinite(value)
                                or (value < before[bound] if bound == "min" else value > before[bound])):
                            problems.append(f"{name} {bound} loosened/removed")
                if before.get("no_significant_drop") and not after.get("no_significant_drop"):
                    problems.append(f"{name} no_significant_drop removed")
    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for sl in spec.get("slices", []):
        name, metric = sl["name"], sl["metric"]
        sid = f"slice:{name}/{metric}"
        a, b = per_item(pr, metric, slice_name=name), per_item(base, metric, slice_name=name)
        val = sum(a.values()) / len(a) if a else None
        failed = val is None or ("min" in sl and val < sl["min"])
        note = ""
        if sl.get("no_significant_drop") and val is not None:
            keys = sorted(set(a) & set(b))
            if len(keys) >= 2:
                d, lo, hi = stats.paired_bootstrap(
                    [a[k] for k in keys], [b[k] for k in keys],
                    n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027),
                    confidence=bs.get("confidence", 0.95))
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                failed = failed or hi < 0
            else:
                note = f"CI unavailable: {len(keys)} paired item(s), need >= 2"
        if failed and sl.get("blocking"):
            blocked.append(sid)
        verdict = ("BLOCK" if sl.get("blocking") else "warn") if failed else "ok"
        value = "MISSING" if val is None else f"{val:.4f}"
        lines.append(f"  {sid:<38} {value:<8} n={len(a)} min={sl.get('min')} {note} {verdict}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027),
                                               confidence=bs.get("confidence", 0.95))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
