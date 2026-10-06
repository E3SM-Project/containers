#!/usr/bin/env python3
"""Report Docker image sizes and largest layers; never pulls or removes images.

With image references: inspect each local image (expanded size, largest layers) and, when it
was pulled from a registry, its compressed size there. With --table: render one markdown
table from the --json reports CI saved for every env and dev image.
"""

import argparse
import json
import subprocess
from pathlib import Path


def docker_json(*args):
    return json.loads(subprocess.check_output(["docker", *args], text=True))


def compressed_size(reference, os_name, architecture):
    """Sum of the compressed layer sizes in the registry, for this platform; None if unknown."""
    try:
        index = json.loads(subprocess.check_output(
            ["docker", "buildx", "imagetools", "inspect", "--raw", reference],
            text=True, stderr=subprocess.DEVNULL,
        ))
        manifest = index
        if "manifests" in index:
            digest = next(
                m["digest"] for m in index["manifests"]
                if (m.get("platform") or {}).get("os") == os_name
                and (m.get("platform") or {}).get("architecture") == architecture
            )
            repository = reference.rsplit(":", 1)[0]
            manifest = json.loads(subprocess.check_output(
                ["docker", "buildx", "imagetools", "inspect", "--raw", f"{repository}@{digest}"],
                text=True, stderr=subprocess.DEVNULL,
            ))
        return sum(layer["size"] for layer in manifest["layers"])
    except (subprocess.CalledProcessError, StopIteration, KeyError, ValueError):
        return None


def inspect(reference, variant=None, kind=None):
    info = docker_json("image", "inspect", reference)[0]
    history = subprocess.check_output(
        ["docker", "history", "--no-trunc", "--human=false", "--format", "{{json .}}", reference],
        text=True,
    )
    layers = [json.loads(line) for line in history.splitlines()]
    return {
        "reference": reference,
        "variant": variant,
        "kind": kind,
        "id": info["Id"],
        "platform": f'{info["Os"]}/{info["Architecture"]}',
        "size_bytes": info["Size"],
        "compressed_bytes": compressed_size(reference, info["Os"], info["Architecture"]),
        "layers": sorted(
            [{"size_bytes": int(layer["Size"]), "command": layer["CreatedBy"]} for layer in layers],
            key=lambda layer: layer["size_bytes"], reverse=True,
        ),
    }


def gb(size):
    return "?" if size is None else f"{size / 1e9:.2f}"


def table(paths):
    """One row per variant and arch: env and dev sizes, and what the dev layer adds."""
    rows = {}
    for path in paths:
        for report in json.loads(Path(path).read_text()):
            # Labelled by the caller (--variant, --kind): the tag alone carries the run's suffix
            # and does not say where the variant name ends.
            row = rows.setdefault((report["variant"], report["platform"]), {})
            row[report["kind"]] = report
    lines = [
        "| variant | platform | env compressed | env expanded | dev compressed | dev expanded | dev adds (expanded) |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for (variant, platform), row in sorted(rows.items()):
        env, dev = row.get("env", {}), row.get("dev", {})
        adds = dev["size_bytes"] - env["size_bytes"] if env and dev else None
        lines.append(
            f'| {variant} | {platform} | {gb(env.get("compressed_bytes"))} | {gb(env.get("size_bytes"))}'
            f' | {gb(dev.get("compressed_bytes"))} | {gb(dev.get("size_bytes"))} | {gb(adds)} |'
        )
    lines.append("\nSizes in GB. Expanded sizes include inherited layers.")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", help="local image references, baseline first; "
                        "with --table, JSON reports")
    parser.add_argument("--json", action="store_true", help="emit exact bytes, IDs and full layer commands")
    parser.add_argument("--table", action="store_true", help="render a markdown table from JSON reports")
    parser.add_argument("--variant", help="label the reports with this variant, for --table")
    parser.add_argument("--kind", choices=["env", "dev"], help="label the reports env or dev, for --table")
    args = parser.parse_args()
    if args.table:
        print(table(args.images))
        return
    reports = [inspect(reference, args.variant, args.kind) for reference in args.images]
    if args.json:
        print(json.dumps(reports, indent=2))
        return
    baseline = reports[0]
    for report in reports:
        print(f'\n{report["reference"]} ({report["platform"]})')
        print(f'  Image size: {report["size_bytes"] / 1e9:.3f} GB (uncompressed layers)')
        if report["compressed_bytes"] is not None:
            print(f'  Registry size: {report["compressed_bytes"] / 1e9:.3f} GB (compressed layers)')
        if report is not baseline and report["platform"] == baseline["platform"]:
            delta = report["size_bytes"] - baseline["size_bytes"]
            print(f'  Change from {baseline["reference"]}: {delta / 1e9:+.3f} GB')
        for layer in report["layers"][:10]:
            print(f'  {layer["size_bytes"] / 1e6:9.1f} MB  {layer["command"]}')
    print("\nSizes include inherited layers; shared layers are not extra disk usage per tag.")


if __name__ == "__main__":
    main()
