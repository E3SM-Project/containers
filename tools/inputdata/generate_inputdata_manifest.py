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
from tools.inputdata.lib.inputdata_validation import InputDataValidationResult, validate_inputdata_reference
from tools.inputdata.lib.url_normalize import filter_candidate_path, is_public_inputdata_url
from tools.inputdata.lib.workflow_parser import TestRecord, build_state_payload, parse_workflows


@dataclass(frozen=True)
class ProvenanceRecord:
    workflow: str
    test: str
    case_dir: str
    component_list_file: str
    manifest: str
    discovery_method: str
    relative_path: str
    validation_status: str
    checked_urls: tuple[str, str]
    validation_message: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate inputdata manifests from E3SM workflows and CIME metadata"
    )
    parser.add_argument(
        "--e3sm-root",
        required=True,
        help="Path to the E3SM checkout that provides workflow files and CIME scripts.",
    )
    parser.add_argument(
        "--test-root",
        required=True,
        help="Directory where CIME test cases are created during discovery.",
    )
    parser.add_argument(
        "--output-root",
        required=True,
        help="Directory used for generated artifacts and temporary discovery output.",
    )
    parser.add_argument(
        "--state-out",
        required=True,
        help="File path for the generated workflow and extraction state JSON.",
    )
    parser.add_argument(
        "--files-out",
        required=True,
        help="File path for the generated full-model inputdata manifest.",
    )
    parser.add_argument(
        "--standalone-files-out",
        required=True,
        help="File path for the generated standalone EAMxx inputdata manifest.",
    )
    parser.add_argument(
        "--provenance-out",
        required=True,
        help="File path for the generated provenance JSON.",
    )
    parser.add_argument(
        "--missing-files-out",
        required=True,
        help="File path for a list of input files that could not be found on either server.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail if workflow parsing or standalone discovery emits warnings.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print progress messages while discovering tests and input files.",
    )
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
    missing_provenance: list[dict[str, object]],
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
        validation = _normalize_and_validate(raw_path, din_loc_root)
        if not validation:
            continue
        method = "standalone-static"
        if source_path.startswith(output_root.as_posix()) or "/ctest-build/" in source_path:
            method = "standalone-config"

        for record in standalone_tests:
            provenance_record = ProvenanceRecord(
                workflow=record.workflow,
                test=record.name,
                case_dir="",
                component_list_file=source_path,
                manifest="files-standalone.txt",
                discovery_method=method,
                relative_path=validation.relative_path,
                validation_status=validation.status,
                checked_urls=validation.checked_urls,
                validation_message=validation.message,
            )
            if validation.status == "missing":
                missing_provenance.append(
                    {
                        "workflow": provenance_record.workflow,
                        "test": provenance_record.test,
                        "case_dir": provenance_record.case_dir,
                        "component_list_file": provenance_record.component_list_file,
                        "manifest": provenance_record.manifest,
                        "discovery_method": provenance_record.discovery_method,
                        "relative_path": provenance_record.relative_path,
                        "checked_urls": list(provenance_record.checked_urls),
                        "validation_status": provenance_record.validation_status,
                        "validation_message": provenance_record.validation_message,
                    }
                )
                continue

            url = validation.resolved_url or validation.checked_urls[0]
            urls.add(url)
            provenance.setdefault(url, []).append(provenance_record)

    return sorted(urls), provenance


def _normalize_and_validate(
    raw_value: str,
    din_loc_root: Path,
) -> Optional[InputDataValidationResult]:
    if not filter_candidate_path(raw_value):
        return None

    validation_result = validate_inputdata_reference(raw_value, din_loc_root)
    if not validation_result:
        return None

    if not validation_result.resolved_url:
        return validation_result

    if not is_public_inputdata_url(validation_result.resolved_url):
        return None

    return validation_result


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
                rec.validation_status,
                rec.relative_path,
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
                "relative_path": rec.relative_path,
                "validation_status": rec.validation_status,
                "checked_urls": list(rec.checked_urls),
                "validation_message": rec.validation_message,
            }
            for rec in entries
        ]
    return payload


def main() -> int:
    args = parse_args()

    e3sm_root = Path(args.e3sm_root).resolve()
    test_root = Path(args.test_root).resolve()
    output_root = Path(args.output_root).resolve()
    din_loc_root = (Path.home() / "e3sm-inputdata-empty").resolve()
    din_loc_root.mkdir(parents=True, exist_ok=True)

    if not e3sm_root.exists():
        print(f"ERROR: --e3sm-root does not exist: {e3sm_root}", file=sys.stderr)
        return 2

    parse_result = parse_workflows(e3sm_root)
    if not parse_result.full_model_tests:
        print("ERROR: no full-model tests extracted from workflows", file=sys.stderr)
        return 3

    state = build_state_payload(parse_result)
    full_urls: set[str] = set()
    full_provenance: dict[str, list[ProvenanceRecord]] = {}
    missing_provenance: list[dict[str, object]] = []

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
                validation = _normalize_and_validate(entry.raw_value, din_loc_root)
                if not validation:
                    continue

                provenance_record = ProvenanceRecord(
                    workflow=test_record.workflow,
                    test=test_record.name,
                    case_dir=test_record.name,
                    component_list_file=entry.component_list_file,
                    manifest="files.txt",
                    discovery_method="cime-buildconf",
                    relative_path=validation.relative_path,
                    validation_status=validation.status,
                    checked_urls=validation.checked_urls,
                    validation_message=validation.message,
                )

                if validation.status == "missing":
                    missing_provenance.append(
                        {
                            "workflow": provenance_record.workflow,
                            "test": provenance_record.test,
                            "case_dir": provenance_record.case_dir,
                            "component_list_file": provenance_record.component_list_file,
                            "manifest": provenance_record.manifest,
                            "discovery_method": provenance_record.discovery_method,
                            "relative_path": provenance_record.relative_path,
                            "checked_urls": list(provenance_record.checked_urls),
                            "validation_status": provenance_record.validation_status,
                            "validation_message": provenance_record.validation_message,
                        }
                    )
                    continue

                url = validation.resolved_url or validation.checked_urls[0]
                full_urls.add(url)
                full_provenance.setdefault(url, []).append(provenance_record)

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
        missing_provenance=missing_provenance,
    )

    combined_provenance = dict(full_provenance)
    for url, entries in standalone_provenance.items():
        combined_provenance.setdefault(url, []).extend(entries)

    files_out = Path(args.files_out)
    standalone_files_out = Path(args.standalone_files_out)
    provenance_out = Path(args.provenance_out)
    missing_files_out = Path(args.missing_files_out)
    state_out = Path(args.state_out)

    missing_relative_paths = sorted(
        {entry["relative_path"] for entry in missing_provenance}
    )

    provenance_payload = _provenance_payload(combined_provenance)
    if missing_provenance:
        provenance_payload["missing"] = missing_provenance

    _write_manifest(sorted(full_urls), files_out)
    _write_manifest(sorted(standalone_urls), standalone_files_out)
    _write_manifest(missing_relative_paths, missing_files_out)
    _write_json(provenance_payload, provenance_out)
    _write_json(state, state_out)

    for entry in sorted(missing_provenance, key=lambda e: e["relative_path"]):
        print(
            f"WARNING: missing inputdata "
            f"path={entry['relative_path']} "
            f"checked={entry['checked_urls']}",
            file=sys.stderr,
        )
    if missing_provenance and args.strict:
        print("ERROR: strict mode enabled and missing inputdata entries were found", file=sys.stderr)
        return 8

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
        f"standalone_urls={len(standalone_urls)} "
        f"missing={len(missing_relative_paths)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
