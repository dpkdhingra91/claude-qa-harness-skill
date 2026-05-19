"""Diff an actual report JSON against a baseline. Structural, not lexical.

Focuses on changes that matter:
  - missing top-level keys
  - type changes (e.g. number → string, list → null)
  - list length swings >50% (a section of the report went empty)
  - empty/null values where the baseline had content

Does NOT flag:
  - exact text differences in transcripts (voice has natural variance)
  - timestamps
  - any keys named 'id', 'createdAt', 'updatedAt', '_*'
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

NOISE_KEYS = {"id", "createdAt", "updatedAt", "timestamp", "ts"}


def walk(obj: Any, path: str = "") -> dict[str, Any]:
    """Flatten an object into {dotted-path: value} for structural comparison."""
    out: dict[str, Any] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in NOISE_KEYS or k.startswith("_"):
                continue
            out.update(walk(v, f"{path}.{k}" if path else k))
    elif isinstance(obj, list):
        out[f"{path}.<len>"] = len(obj)
        # walk only the first 3 items — structure check, not content
        for i, item in enumerate(obj[:3]):
            out.update(walk(item, f"{path}[{i}]"))
    else:
        out[path] = type(obj).__name__ if obj is not None else "null"
    return out


def diff(baseline: dict, actual: dict) -> list[dict]:
    """Return a list of {kind, path, baseline, actual} entries for material changes."""
    b = walk(baseline)
    a = walk(actual)
    findings: list[dict] = []

    for path in sorted(set(b.keys()) | set(a.keys())):
        bv = b.get(path)
        av = a.get(path)
        if path.endswith(".<len>"):
            if bv is None and av is None:
                continue
            if bv is None or av is None or bv == 0:
                continue  # skip baseline-was-empty noise
            ratio = av / bv if bv else 0
            if ratio < 0.5 or ratio > 2.0:
                findings.append({
                    "kind": "list-length-shift",
                    "path": path.removesuffix(".<len>"),
                    "baseline": bv,
                    "actual": av,
                })
        elif bv != av:
            if bv is not None and av is None:
                findings.append({"kind": "missing-in-actual", "path": path, "baseline": bv, "actual": None})
            elif bv is None and av is not None:
                findings.append({"kind": "added-in-actual", "path": path, "baseline": None, "actual": av})
            elif bv != av:
                findings.append({"kind": "type-change", "path": path, "baseline": bv, "actual": av})

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, help="Path to baseline JSON")
    parser.add_argument("--actual", required=True, help="Path to actual JSON")
    args = parser.parse_args()

    baseline = json.loads(Path(args.baseline).read_text())
    actual = json.loads(Path(args.actual).read_text())

    findings = diff(baseline, actual)

    if not findings:
        print(json.dumps({"status": "clean", "findings": []}, indent=2))
        return 0

    print(json.dumps({"status": "drift", "count": len(findings), "findings": findings}, indent=2))
    return 0 if len(findings) <= 2 else 1


if __name__ == "__main__":
    sys.exit(main())
