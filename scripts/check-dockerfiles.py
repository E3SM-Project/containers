#!/usr/bin/env python3
"""Check this repository's Dockerfile RUN syntax without building the images."""

import json
from pathlib import Path
import subprocess
import sys


def instructions(path):
    """Join Dockerfile continuation lines, ignoring comment-only lines."""
    parts = []
    start = 0
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not parts:
            start = number
        continued = line.rstrip().endswith("\\")
        parts.append(line.rstrip()[:-1] if continued else line)
        if not continued:
            yield start, " ".join(parts)
            parts = []
    if parts:
        raise ValueError(f"{path}:{start}: unterminated continuation")


def main():
    paths = [Path(p) for p in sys.argv[1:]] or sorted(Path("ghci").glob("*/Dockerfile"))
    if not paths:
        sys.exit("No Dockerfiles found; run from the repository root.")
    checked = 0
    errors = []
    for path in paths:
        try:
            for line, instruction in instructions(path):
                op, _, body = instruction.partition(" ")
                body = body.lstrip()
                if op.upper() in {"RUN", "CMD", "ENTRYPOINT", "SHELL"} and body.startswith("["):
                    value = json.loads(body)
                    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                        raise ValueError(f"{path}:{line}: expected a JSON array of strings")
                elif op.upper() == "RUN":
                    # All recipes use sh or bash. Bash parses the initial POSIX RUNs too.
                    result = subprocess.run(["bash", "-n"], input=body, text=True, capture_output=True)
                    if result.returncode:
                        errors.append(f"{path}:{line}: {result.stderr.strip()}")
                    checked += 1
        except (ValueError, OSError) as exc:
            errors.append(str(exc))
    if errors:
        sys.exit("\n".join(errors))
    print(f"Checked {checked} shell RUN instructions in {len(paths)} Dockerfiles.")


if __name__ == "__main__":
    main()
