#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

TRIGGER_FILES = [
    "inputdata/files.txt",
    "inputdata/files-standalone.txt",
    "inputdata/files-missing.txt",
]

ADDITIONAL_PR_FILES = [
    "inputdata/e3sm-workflow-state.json",
    "inputdata/provenance.json",
]

PR_FILES = [*TRIGGER_FILES, *ADDITIONAL_PR_FILES]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build PR body content for inputdata manifest updates"
    )
    parser.add_argument(
        "--output-path",
        required=True,
        help="Path where the markdown PR body should be written.",
    )
    parser.add_argument(
        "--state-path",
        required=True,
        help="Path to inputdata/e3sm-workflow-state.json.",
    )
    return parser.parse_args()


def _git_numstat(paths: list[str]) -> str:
    output = subprocess.check_output(
        ["git", "diff", "--numstat", "--", *paths],
        text=True,
    )
    return output.strip()


def _render_body(state: dict, numstat: str) -> str:
    tests = state.get("extracted_tests", [])
    e3sm_sha = state.get("e3sm_sha", "unknown")

    lines: list[str] = []
    lines.append("Automated inputdata manifest refresh from E3SM workflows.")
    lines.append("")
    lines.append("Source snapshot")
    lines.append(f"- E3SM SHA: {e3sm_sha}")
    lines.append(f"- Extracted tests: {len(tests)}")
    lines.append("")
    lines.append("Changed files")
    if numstat:
        for row in numstat.splitlines():
            added, removed, path = row.split("\t", maxsplit=2)
            lines.append(f"- {path}: +{added} / -{removed} lines")
    else:
        lines.append("- No managed file changes detected")
    lines.append("")
    lines.append("PR trigger files")
    for path in TRIGGER_FILES:
        lines.append(f"- {path}")
    lines.append("")
    lines.append("Additional files included when a PR is opened")
    for path in ADDITIONAL_PR_FILES:
        lines.append(f"- {path}")
    lines.append("")
    lines.append("Review guidance")
    lines.append("- Please review the provenance and missing-file updates before merge.")
    lines.append(
        "- Merging this PR will trigger normal inputdata image build/publish workflows."
    )

    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    output_path = Path(args.output_path)
    state_path = Path(args.state_path)

    with state_path.open("r", encoding="utf-8") as file:
        state = json.load(file)

    numstat = _git_numstat(PR_FILES)
    body = _render_body(state, numstat)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(body, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
