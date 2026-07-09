from __future__ import annotations

import glob
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class InputListEntry:
    case_dir: str
    component_list_file: str
    raw_value: str


@dataclass(frozen=True)
class CaseResult:
    test_name: str
    workflow: str
    success: bool
    case_dirs: list[str]
    started_at_utc: str
    finished_at_utc: str
    error: Optional[str] = None


def run_create_test(
    e3sm_root: Path,
    test_name: str,
    test_root: Path,
    output_root: Path,
    din_loc_root: Path,
    workflow: str,
) -> CaseResult:
    create_test = e3sm_root / "cime" / "scripts" / "create_test"
    if not create_test.exists():
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return CaseResult(
            test_name=test_name,
            workflow=workflow,
            success=False,
            case_dirs=[],
            started_at_utc=now,
            finished_at_utc=now,
            error=f"Missing create_test script: {create_test}",
        )

    before = set(discover_case_dirs(test_root))
    started_at_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    command = [
        str(create_test),
        test_name,
        "--no-build",
        "--no-run",
        "--namelists-only",
        "--test-root",
        str(test_root),
        "--output-root",
        str(output_root),
        "--input-dir",
        str(din_loc_root),
        "--wait",
    ]

    process = subprocess.run(
        command,
        cwd=str(e3sm_root),
        text=True,
        capture_output=True,
    )
    finished_at_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    after = set(discover_case_dirs(test_root))
    new_case_dirs = sorted(after - before)
    case_dirs = new_case_dirs if new_case_dirs else sorted(after)

    if process.returncode != 0:
        stderr_tail = (process.stderr or process.stdout or "").strip().splitlines()
        tail = "\n".join(stderr_tail[-10:]) if stderr_tail else "create_test failed"
        return CaseResult(
            test_name=test_name,
            workflow=workflow,
            success=False,
            case_dirs=case_dirs,
            started_at_utc=started_at_utc,
            finished_at_utc=finished_at_utc,
            error=tail,
        )

    return CaseResult(
        test_name=test_name,
        workflow=workflow,
        success=True,
        case_dirs=case_dirs,
        started_at_utc=started_at_utc,
        finished_at_utc=finished_at_utc,
    )


def discover_case_dirs(test_root: Path) -> list[str]:
    pattern = str(test_root / "**" / "Buildconf")
    buildconf_dirs = [Path(path) for path in glob.glob(pattern, recursive=True)]
    case_dirs = sorted({str(path.parent) for path in buildconf_dirs})
    return case_dirs


def _extract_candidate_from_line(line: str) -> list[str]:
    line = line.split("#", 1)[0].strip()
    if not line:
        return []

    if "=" in line:
        _, rhs = line.split("=", 1)
    else:
        rhs = line

    raw_tokens = rhs.replace(",", " ").split()
    tokens: list[str] = []
    for token in raw_tokens:
        cleaned = token.strip().strip('"').strip("'")
        if not cleaned:
            continue
        tokens.append(cleaned)
    return tokens


def parse_input_data_lists(case_dir: Path) -> list[InputListEntry]:
    entries: list[InputListEntry] = []
    buildconf = case_dir / "Buildconf"
    for list_file in sorted(buildconf.glob("*.input_data_list")):
        with list_file.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                for token in _extract_candidate_from_line(line):
                    entries.append(
                        InputListEntry(
                            case_dir=str(case_dir),
                            component_list_file=list_file.name,
                            raw_value=token,
                        )
                    )
    return entries
