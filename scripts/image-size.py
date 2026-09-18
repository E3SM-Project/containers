#!/usr/bin/env python3
"""Report local Docker image sizes and largest layers; never pulls or removes images."""

import argparse
import json
import subprocess


def docker_json(*args):
    return json.loads(subprocess.check_output(["docker", *args], text=True))


def inspect(reference):
    info = docker_json("image", "inspect", reference)[0]
    history = subprocess.check_output(
        ["docker", "history", "--no-trunc", "--human=false", "--format", "{{json .}}", reference],
        text=True,
    )
    layers = [json.loads(line) for line in history.splitlines()]
    return {
        "reference": reference,
        "id": info["Id"],
        "platform": f'{info["Os"]}/{info["Architecture"]}',
        "size_bytes": info["Size"],
        "layers": sorted(
            [{"size_bytes": int(layer["Size"]), "command": layer["CreatedBy"]} for layer in layers],
            key=lambda layer: layer["size_bytes"], reverse=True,
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", help="local image references, baseline first")
    parser.add_argument("--json", action="store_true", help="emit exact bytes, IDs and full layer commands")
    args = parser.parse_args()
    reports = [inspect(reference) for reference in args.images]
    if args.json:
        print(json.dumps(reports, indent=2))
        return
    baseline = reports[0]
    for report in reports:
        print(f'\n{report["reference"]} ({report["platform"]})')
        print(f'  Image size: {report["size_bytes"] / 1e9:.3f} GB (uncompressed layers)')
        if report is not baseline and report["platform"] == baseline["platform"]:
            delta = report["size_bytes"] - baseline["size_bytes"]
            print(f'  Change from {baseline["reference"]}: {delta / 1e9:+.3f} GB')
        for layer in report["layers"][:10]:
            print(f'  {layer["size_bytes"] / 1e6:9.1f} MB  {layer["command"]}')
    print("\nSizes include inherited layers; shared layers are not extra disk usage per tag.")


if __name__ == "__main__":
    main()
