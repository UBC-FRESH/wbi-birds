"""Standalone parity check: engine results vs a legacy reference table.

Usage:
    python scripts/parity_check.py <instance> <reference.csv> [--label NAME] [--strict]

Writes ``<instance>/results/parity/<label>-parity.{json,md}`` and exits non-zero
only in ``--strict`` mode when any record fails tolerance.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from wbi_birds.parity import compare_instance_results, write_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("instance", type=Path, help="Instance root (contains results/scenarios/).")
    parser.add_argument("reference", type=Path, help="Long-format reference table CSV.")
    parser.add_argument("--label", default="suite", help="Report label (default: suite).")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when any record fails tolerance.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = compare_instance_results(args.instance, args.reference)
    artifacts = write_report(report, args.instance / "results", label=args.label)
    summary = report.summary()
    print(
        f"parity: compared={summary['n_compared']} passed={summary['n_passed']} "
        f"failed={summary['n_failed']} records={summary['n_records']}"
    )
    for metric, stats in summary["per_metric"].items():
        print(
            f"  {metric}: n={stats['n']} failed={stats['failed']} "
            f"max_abs_diff={stats['max_abs_diff']:.6g} "
            f"max_rel_diff={stats['max_rel_diff']:.6g}"
        )
    for key, value in sorted(artifacts.items()):
        print(f"  report ({key}): {args.instance / 'results' / value}")
    if args.strict and summary["n_failed"] > 0:
        print("strict mode: parity failures present")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
