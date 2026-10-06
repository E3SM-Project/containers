#!/usr/bin/env python3
"""Verify the OCI metadata of published multi-arch images; needs docker buildx and registry access.

Checks, for every given image reference, that the manifest index carries the expected
annotations, lists exactly the expected platforms, and that each platform's image config
carries the expected labels (not the base image's).
"""

import argparse
import json
import subprocess
import sys

PREFIX = "org.opencontainers.image."
ARCHES = {"x86_64": "amd64", "aarch64": "arm64"}


def imagetools(*args):
    return subprocess.check_output(["docker", "buildx", "imagetools", "inspect", *args], text=True)


def platform_name(platform):
    return f'{platform.get("os")}/{platform.get("architecture")}'


def check_fields(where, actual, expected, errors, created=True):
    for key, want in expected.items():
        got = actual.get(PREFIX + key)
        if got != want:
            errors.append(f"{where}: {PREFIX}{key} is {got!r}, expected {want!r}")
    if created and not actual.get(PREFIX + "created"):
        errors.append(f"{where}: {PREFIX}created is missing")


def check_image(reference, expected, arches):
    errors = []
    index = json.loads(imagetools("--raw", reference))
    if "manifests" not in index:
        return [f"{reference}: not a manifest index"]
    check_fields(f"{reference} index annotations", index.get("annotations") or {}, expected, errors, created=False)

    found = {}
    for manifest in index["manifests"]:
        platform = manifest.get("platform") or {}
        if platform.get("os") == "unknown":
            continue  # attestation manifest
        name = platform_name(platform)
        found[name] = manifest["digest"]
    want = {f"linux/{ARCHES[arch]}" for arch in arches}
    if set(found) != want:
        errors.append(f"{reference}: platforms are {sorted(found)}, expected {sorted(want)}")

    repository = reference.rsplit(":", 1)[0]
    for name, digest in sorted(found.items()):
        image = json.loads(imagetools(f"{repository}@{digest}", "--format", "{{json .Image}}"))
        labels = (image.get("config") or {}).get("Labels") or {}
        check_fields(f"{reference} {name} config labels", labels, expected, errors)
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", help="image references (repository:tag)")
    parser.add_argument("--arches", required=True, help='JSON array of arches, e.g. \'["x86_64"]\'')
    parser.add_argument("--title", required=True)
    parser.add_argument("--description", default="")
    parser.add_argument("--revision", required=True)
    parser.add_argument("--source", required=True)
    args = parser.parse_args()

    expected = {"title": args.title, "revision": args.revision, "source": args.source}
    if args.description:
        expected["description"] = args.description
    arches = json.loads(args.arches)
    unknown = [arch for arch in arches if arch not in ARCHES]
    if unknown:
        sys.exit(f"unsupported arches: {unknown}")

    errors = []
    for reference in args.images:
        found = check_image(reference, expected, arches)
        print(f"{reference}: {'FAILED' if found else 'ok'}")
        errors += found
    for error in errors:
        print(f"::error::{error}")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
