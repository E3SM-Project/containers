from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


CREATE_TEST_PATTERN = re.compile(
    r"(?:^|\s)(?:\./)?cime/scripts/create_test\s+(?P<test>[A-Za-z0-9_\-.+]+)|"
    r"(?:^|\s)create_test\s+(?P<test2>[A-Za-z0-9_\-.+]+)"
)
MATRIX_FULL_NAME_PATTERN = re.compile(
    r"full_name\s*:\s*[\"']?(?P<test>[A-Za-z0-9_\-.+]+)[\"']?"
)
STANDALONE_PATTERN = re.compile(r"test-all-eamxx")


@dataclass(frozen=True)
class TestRecord:
    workflow: str
    kind: str
    name: str


@dataclass(frozen=True)
class WorkflowParseResult:
    e3sm_sha: str
    workflow_hashes: dict[str, str]
    full_model_tests: list[TestRecord]
    standalone_tests: list[TestRecord]
    warnings: list[str]



def collect_workflow_files(e3sm_root: Path) -> list[Path]:
    workflows_dir = e3sm_root / ".github" / "workflows"
    files = sorted(workflows_dir.glob("*.yml")) + sorted(workflows_dir.glob("*.yaml"))
    return sorted(set(files))


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _get_e3sm_sha(e3sm_root: Path) -> str:
    try:
        output = subprocess.check_output(
            ["git", "-C", str(e3sm_root), "rev-parse", "HEAD"],
            text=True,
        )
        return output.strip()
    except Exception:
        return "unknown"


def _parse_create_test_lines(workflow_rel: str, content: str) -> Iterable[TestRecord]:
    seen: set[str] = set()
    for line in content.splitlines():
        match = CREATE_TEST_PATTERN.search(line)
        if not match:
            continue
        test_name = match.group("test") or match.group("test2")
        if not test_name:
            continue
        test_name = test_name.strip().strip('"').strip("'")
        if test_name not in seen:
            seen.add(test_name)
            yield TestRecord(workflow=workflow_rel, kind="create_test", name=test_name)



def _parse_matrix_full_names(workflow_rel: str, content: str) -> Iterable[TestRecord]:
    seen: set[str] = set()
    for line in content.splitlines():
        match = MATRIX_FULL_NAME_PATTERN.search(line)
        if not match:
            continue
        test_name = match.group("test").strip()
        if test_name not in seen:
            seen.add(test_name)
            yield TestRecord(workflow=workflow_rel, kind="matrix_full_name", name=test_name)



def _parse_standalone(workflow_rel: str, content: str) -> Iterable[TestRecord]:
    lines = content.splitlines()
    for idx, line in enumerate(lines):
        if not STANDALONE_PATTERN.search(line):
            continue
        name = f"standalone_ref_line_{idx + 1}"
        yield TestRecord(workflow=workflow_rel, kind="standalone_ref", name=name)



def parse_workflows(e3sm_root: Path) -> WorkflowParseResult:
    workflow_files = collect_workflow_files(e3sm_root)
    if not workflow_files:
        raise FileNotFoundError("No workflow YAML files found under E3SM/.github/workflows")

    workflow_hashes: dict[str, str] = {}
    full_records: set[TestRecord] = set()
    standalone_records: set[TestRecord] = set()
    warnings: list[str] = []

    for path in workflow_files:
        relative = path.relative_to(e3sm_root).as_posix()
        workflow_hashes[relative] = _hash_file(path)
        content = path.read_text(encoding="utf-8", errors="replace")

        full_before = len(full_records)
        for record in _parse_create_test_lines(relative, content):
            full_records.add(record)
        for record in _parse_matrix_full_names(relative, content):
            full_records.add(record)

        for record in _parse_standalone(relative, content):
            standalone_records.add(record)

        if len(full_records) == full_before and "create_test" in content:
            warnings.append(f"Could not confidently parse create_test syntax in {relative}")

    return WorkflowParseResult(
        e3sm_sha=_get_e3sm_sha(e3sm_root),
        workflow_hashes=dict(sorted(workflow_hashes.items())),
        full_model_tests=sorted(full_records, key=lambda r: (r.workflow, r.kind, r.name)),
        standalone_tests=sorted(standalone_records, key=lambda r: (r.workflow, r.kind, r.name)),
        warnings=sorted(set(warnings)),
    )


def build_state_payload(parse_result: WorkflowParseResult, e3sm_ref: str = "master") -> dict:
    extracted_tests = [
        {"workflow": rec.workflow, "kind": rec.kind, "name": rec.name}
        for rec in parse_result.full_model_tests + parse_result.standalone_tests
    ]
    extracted_tests = sorted(
        extracted_tests,
        key=lambda r: (r["workflow"], r["kind"], r["name"]),
    )

    encoded = json.dumps(extracted_tests, sort_keys=True, separators=(",", ":"))
    extracted_hash = hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    return {
        "e3sm_ref": e3sm_ref,
        "e3sm_sha": parse_result.e3sm_sha,
        "workflow_files_sha256": parse_result.workflow_hashes,
        "extracted_tests_sha256": extracted_hash,
        "extracted_tests": extracted_tests,
    }
