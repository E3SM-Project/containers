#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from tools.inputdata.lib.cime_manifest import parse_input_data_lists, run_create_test
from tools.inputdata.lib.url_normalize import (
    filter_candidate_path,
    is_public_inputdata_url,
    normalize_to_din_relative,
    to_public_inputdata_url,
)
from tools.inputdata.lib.workflow_parser import TestRecord, build_state_payload, parse_workflows


@dataclass(frozen=True)
class ProvenanceRecord:
    workflow: str
    test: str
    case_dir: str
    component_list_file: str
    manifest: str
    discovery_method: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate inputdata manifests from E3SM workflows and CIME metadata"
    )
    parser.add_argument("--e3sm-root", required=True)
    parser.add_argument("--din-loc-root", required=True)
    parser.add_argument("--test-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--state-out", required=True)
    parser.add_argument("--files-out", required=True)
    parser.add_argument("--standalone-files-out", required=True)
    parser.add_argument("--provenance-out", required=True)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def _write_manifest(urls: list[str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(urls)
    if text:
        text += "\n"
    path.write_text(text, encoding="utf-8")


def _write_json(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _log(message: str, verbose: bool) -> None:
    if verbose:
        print(message)


def _collect_standalone_candidate_paths(e3sm_root: Path) -> list[tuple[str, str]]:
    """Return (source_path, candidate_input_path) pairs from static scans."""
    candidates: set[tuple[str, str]] = set()

    static_globs = [
        "components/eamxx/scripts/**/*",
        "components/eamxx/**/*.yaml",
        "components/eamxx/**/*.yml",
        ".github/actions/test-all-eamxx/**/*",
    ]

    path_pattern = re.compile(r"(?P<path>(?:\$\{?DIN_LOC_ROOT\}?/)?[A-Za-z0-9_./+-]+\.(?:nc|txt|xml|yaml|yml|json|dat|h5))")

    for pattern in static_globs:
        for file_path in sorted(e3sm_root.glob(pattern)):
            if not file_path.is_file():
                continue
            rel_source = file_path.relative_to(e3sm_root).as_posix()
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            for line in content.splitlines():
                if "check-input" not in line and "DIN_LOC_ROOT" not in line and "inputdata" not in line:
                    continue
                for match in path_pattern.finditer(line):
                    raw = match.group("path")
                    candidates.add((rel_source, raw))

    return sorted(candidates)


def _run_standalone_config_mode(e3sm_root: Path, output_root: Path) -> tuple[bool, list[str]]:
    """Best-effort config-only run for standalone EAMxx discovery."""
    script = e3sm_root / "components" / "eamxx" / "scripts" / "test-all-eamxx"
    if not script.exists():
        return False, [f"Missing standalone script: {script}"]

    output_root.mkdir(parents=True, exist_ok=True)
    command = [str(script), "--help"]
    try:
        help_proc = subprocess.run(
            command,
            cwd=str(e3sm_root),
            text=True,
            capture_output=True,
        )
    except OSError as exc:
        return False, [f"Failed to execute standalone script: {exc}"]

    supported_flags = help_proc.stdout + "\n" + help_proc.stderr
    run_command = [str(script)]
    if "--configure-only" in supported_flags:
        run_command.append("--configure-only")
    elif "--config-only" in supported_flags:
        run_command.append("--config-only")
    elif "--dry-run" in supported_flags:
        run_command.append("--dry-run")

    if "--work-dir" in supported_flags:
        run_command.extend(["--work-dir", str(output_root / "standalone-work")])

    proc = subprocess.run(
        run_command,
        cwd=str(e3sm_root),
        text=True,
        capture_output=True,
    )

    messages: list[str] = []
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()
        messages.append("standalone config mode failed")
        messages.extend(tail[-10:])
        return False, messages

    return True, messages


def _scan_option_b_artifacts(e3sm_root: Path, output_root: Path) -> list[tuple[str, str]]:
    candidates: set[tuple[str, str]] = set()
    search_roots = [
        output_root,
        e3sm_root / "components" / "eamxx" / "ctest-build",
        e3sm_root / "components" / "eamxx" / "build",
    ]
    path_pattern = re.compile(r"(?P<path>(?:\$\{?DIN_LOC_ROOT\}?/)?[A-Za-z0-9_./+-]+\.(?:nc|txt|xml|yaml|yml|json|dat|h5))")

    for root in search_roots:
        if not root.exists():
            continue
        for file_path in sorted(root.rglob("*")):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in {
                ".txt",
                ".cmake",
                ".cfg",
                ".yaml",
                ".yml",
                ".log",
                ".sh",
                ".json",
            }:
                continue
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for line in content.splitlines():
                if "DIN_LOC_ROOT" not in line and "inputdata" not in line:
                    continue
                for match in path_pattern.finditer(line):
                    raw = match.group("path")
                    candidates.add((file_path.as_posix(), raw))

    return sorted(candidates)


def _standalone_from_workflow_records(
    e3sm_root: Path,
    records: list[TestRecord],
    din_loc_root: Path,
    output_root: Path,
    warnings: list[str],
) -> tuple[list[str], dict[str, list[ProvenanceRecord]]]:
    urls: set[str] = set()
    provenance: dict[str, list[ProvenanceRecord]] = {}
    standalone_tests = records or [
        TestRecord(workflow="components/eamxx", kind="standalone_scan", name="standalone-static")
    ]

    static_candidates = _collect_standalone_candidate_paths(e3sm_root)
    option_b_ok, option_b_messages = _run_standalone_config_mode(e3sm_root, output_root)
    if not option_b_ok:
        warnings.extend(option_b_messages)

    option_b_candidates = _scan_option_b_artifacts(e3sm_root, output_root) if option_b_ok else []
    all_candidates = static_candidates + option_b_candidates
    if not all_candidates:
        return [], {}

    for source_path, raw_path in all_candidates:
        url = _normalize_and_collect(raw_path, din_loc_root)
        if not url:
            continue
        urls.add(url)
        method = "standalone-static"
        if source_path.startswith(output_root.as_posix()) or "/ctest-build/" in source_path:
            method = "standalone-config"
        for record in standalone_tests:
            provenance.setdefault(url, []).append(
                ProvenanceRecord(
                    workflow=record.workflow,
                    test=record.name,
                    case_dir="",
                    component_list_file=source_path,
                    manifest="files-standalone.txt",
                    discovery_method=method,
                )
            )

    return sorted(urls), provenance


def _normalize_and_collect(
    raw_value: str,
    din_loc_root: Path,
) -> Optional[str]:
    if not filter_candidate_path(raw_value):
        return None

    relative = normalize_to_din_relative(raw_value, din_loc_root)
    if not relative:
        return None

    url = to_public_inputdata_url(relative)
    if not is_public_inputdata_url(url):
        return None

    return url


def _provenance_payload(data: dict[str, list[ProvenanceRecord]]) -> dict[str, list[dict]]:
    payload: dict[str, list[dict]] = {}
    for url in sorted(data):
        entries = sorted(
            data[url],
            key=lambda rec: (
                rec.workflow,
                rec.test,
                rec.component_list_file,
                rec.case_dir,
                rec.manifest,
                rec.discovery_method,
            ),
        )
        payload[url] = [
            {
                "workflow": rec.workflow,
                "test": rec.test,
                "case_dir": rec.case_dir,
                "component_list_file": rec.component_list_file,
                "manifest": rec.manifest,
                "discovery_method": rec.discovery_method,
            }
            for rec in entries
        ]
    return payload


def main() -> int:
    args = parse_args()

    e3sm_root = Path(args.e3sm_root).resolve()
    din_loc_root = Path(args.din_loc_root).resolve()
    test_root = Path(args.test_root).resolve()
    output_root = Path(args.output_root).resolve()

    if not e3sm_root.exists():
        print(f"ERROR: --e3sm-root does not exist: {e3sm_root}", file=sys.stderr)
        return 2

    parse_result = parse_workflows(e3sm_root)
    if not parse_result.full_model_tests:
        print("ERROR: no full-model tests extracted from workflows", file=sys.stderr)
        return 3

    state = build_state_payload(parse_result)
    state["generated_at_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    full_urls: set[str] = set()
    full_provenance: dict[str, list[ProvenanceRecord]] = {}

    success_count = 0
    failure_count = 0

    for test_record in parse_result.full_model_tests:
        _log(f"Running create_test for {test_record.name}", args.verbose)
        result = run_create_test(
            e3sm_root=e3sm_root,
            test_name=test_record.name,
            test_root=test_root,
            output_root=output_root,
            din_loc_root=din_loc_root,
            workflow=test_record.workflow,
        )

        if not result.success:
            failure_count += 1
            print(
                "WARNING: create_test failed "
                f"test={test_record.name} "
                f"started={result.started_at_utc} "
                f"finished={result.finished_at_utc} "
                f"error={result.error}",
                file=sys.stderr,
            )
            continue

        success_count += 1

        for case_dir_value in result.case_dirs:
            case_dir = Path(case_dir_value)
            entries = parse_input_data_lists(case_dir)
            for entry in entries:
                url = _normalize_and_collect(entry.raw_value, din_loc_root)
                if not url:
                    continue
                full_urls.add(url)
                full_provenance.setdefault(url, []).append(
                    ProvenanceRecord(
                        workflow=test_record.workflow,
                        test=test_record.name,
                        case_dir=entry.case_dir,
                        component_list_file=entry.component_list_file,
                        manifest="files.txt",
                        discovery_method="cime-buildconf",
                    )
                )

    if success_count == 0:
        print("ERROR: CIME case generation failed for all tests", file=sys.stderr)
        return 4

    if not full_urls:
        print("ERROR: resulting full-model manifest would be empty", file=sys.stderr)
        return 5

    standalone_warnings: list[str] = []
    standalone_urls, standalone_provenance = _standalone_from_workflow_records(
        e3sm_root=e3sm_root,
        records=parse_result.standalone_tests,
        din_loc_root=din_loc_root,
        output_root=output_root,
        warnings=standalone_warnings,
    )

    combined_provenance = dict(full_provenance)
    for url, entries in standalone_provenance.items():
        combined_provenance.setdefault(url, []).extend(entries)

    files_out = Path(args.files_out)
    standalone_files_out = Path(args.standalone_files_out)
    provenance_out = Path(args.provenance_out)
    state_out = Path(args.state_out)

    _write_manifest(sorted(full_urls), files_out)
    _write_manifest(sorted(standalone_urls), standalone_files_out)
    _write_json(_provenance_payload(combined_provenance), provenance_out)
    _write_json(state, state_out)

    if parse_result.warnings:
        for warning in parse_result.warnings:
            print(f"WARNING: {warning}", file=sys.stderr)
        if args.strict:
            print("ERROR: strict mode enabled and parser warnings were present", file=sys.stderr)
            return 6

    if standalone_warnings:
        for warning in standalone_warnings:
            print(f"WARNING: {warning}", file=sys.stderr)
        if args.strict:
            print("ERROR: strict mode enabled and standalone warnings were present", file=sys.stderr)
            return 7

    print(
        "SUMMARY "
        f"full_tests={len(parse_result.full_model_tests)} "
        f"full_success={success_count} "
        f"full_failed={failure_count} "
        f"full_urls={len(full_urls)} "
        f"standalone_refs={len(parse_result.standalone_tests)} "
        f"standalone_urls={len(standalone_urls)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
