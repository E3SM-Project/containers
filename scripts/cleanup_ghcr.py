#!/usr/bin/env python3
"""Delete GHCR package versions this repository's CI no longer needs.

    cleanup_ghcr.py pr-closed   delete the versions a just-closed PR published
    cleanup_ghcr.py untagged    delete untagged and stale merge-queue versions older than HOURS_OLD

Environment: GITHUB_TOKEN, GITHUB_OWNER, PR_NUMBER (pr-closed), HOURS_OLD (untagged, default
48), DRY_RUN=true to only log. The selection rules are the pure functions at the top, tested by
scripts/test_cleanup_ghcr.py; everything below them is the REST and registry I/O.
"""

import base64
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

# The packages this repository publishes and cleans. A package not listed here is never
# touched -- e.g. the Spack binary cache (e3sm-spack-buildcache), which spack manages itself.
PACKAGES = [
    "e3sm-image",
    "e3sm-image-buildcache",  # BuildKit registry cache (build-multiarch.yaml's CACHE)
    # The old names, no longer published to: their PR, merge queue and cache tags from before
    # the rename still need to age out.
    "e3sm-ghci",
    "e3sm-ghci-buildcache",
]

# BuildKit cache tags carry a trailing arch (<tag>-pr-<N>-<arch>), image tags do not.
ARCH = r"(?:-(?:x86_64|aarch64))?"
PR_TAG = re.compile(rf"-pr-\d+{ARCH}$")
# CI's staging tags (see ghci.yaml's `suffix` job): merge_group runs publish under
# <tag>-mg-<sha>, and tags, dispatches and untested pushes to main under <tag>-rc-<run_id>
# before `promote` retags what passed. There is no single PR to delete them on (a merge_group
# run can batch several PRs), so they age out instead.
STAGING_TAG = re.compile(rf"-(?:mg-[0-9a-f]{{40}}|rc-\d+){ARCH}$")


def tags(version):
    return version.get("metadata", {}).get("container", {}).get("tags", [])


def closed_pr_versions(versions, pr):
    """The versions to delete when PR #<pr> closes.

    Only versions whose every tag is this PR's: a fully cached PR build is byte-identical to
    main's, so one digest may hold both `base` and `base-pr-N`, and deleting it would take the
    main tag down too.
    """
    own = re.compile(rf"-pr-{pr}{ARCH}$")
    return [v for v in versions if tags(v) and all(own.search(t) for t in tags(v))]


def is_stale_staging(version):
    """Tagged only with CI staging tags: at least one -mg-/-rc-, and any others staging or -pr-.

    A merge_group build can be byte-identical to a pull_request build, so GHCR puts both tags
    on one version; without accepting -pr- next to -mg- that version would never be deleted. A
    version tagged only -pr-<N> (an open PR) is left to the pr-closed mode.
    """
    t = tags(version)
    return (bool(t) and any(STAGING_TAG.search(x) for x in t)
            and all(STAGING_TAG.search(x) or PR_TAG.search(x) for x in t))


def deletable(versions, references, now, min_hours):
    """The untagged and stale staging versions older than min_hours that nothing uses.

    The per-arch images (and attestations) of a multi-arch tag are themselves untagged
    versions, so every digest a kept tagged version references is in use. `references` maps
    each tagged version's digest to the digests it references; a missing entry means its
    manifest could not be read, and then nothing is deleted (returns None), since what it
    references is unknown.

    A live BuildKit cache tag is kept like any other tag. When cache-to moves the tag, the
    superseded digest becomes untagged and goes like any other untagged version.
    """
    in_use = set()
    for v in versions:
        if not tags(v):
            continue
        if v["name"] not in references:
            return None
        if not is_stale_staging(v):
            in_use.add(v["name"])
        in_use.update(references[v["name"]])

    def old(v):
        created = datetime.fromisoformat(v["created_at"].replace("Z", "+00:00"))
        return (now - created).total_seconds() / 3600 > min_hours

    return [v for v in versions
            if (not tags(v) or is_stale_staging(v)) and v["name"] not in in_use and old(v)]


# ---- I/O --------------------------------------------------------------------------------------

API = "https://api.github.com"
MANIFEST_TYPES = ",".join([
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
])


def request(method, url, headers):
    with urllib.request.urlopen(urllib.request.Request(url, method=method, headers=headers)) as r:
        body = r.read()
        return (json.loads(body) if body else None), r.headers.get("Link", "")


class Ghcr:
    def __init__(self, owner, token):
        self.owner, self.token = owner, token
        self.headers = {"Accept": "application/vnd.github+json",
                        "Authorization": f"Bearer {token}",
                        "X-GitHub-Api-Version": "2022-11-28"}

    def _versions_url(self, scope, package):
        return f"{API}/{scope}/{self.owner}/packages/container/{package}/versions"

    def versions(self, package, scopes):
        """All versions of a package, trying each scope (orgs, users) in turn."""
        error = None
        for scope in scopes:
            try:
                versions, url = [], f"{self._versions_url(scope, package)}?per_page=100"
                while url:
                    page, link = request("GET", url, self.headers)
                    versions += page
                    url = next(iter(re.findall(r'<([^>]+)>;\s*rel="next"', link)), None)
                return versions
            except OSError as e:
                error = e
        raise error

    def delete(self, package, version_id, scopes):
        for i, scope in enumerate(scopes):
            try:
                request("DELETE", f"{self._versions_url(scope, package)}/{version_id}", self.headers)
                return
            except OSError:
                if i == len(scopes) - 1:
                    raise

    def references(self, package, digest):
        """The digests a manifest list references (none for a single-image manifest)."""
        url = f"https://ghcr.io/v2/{self.owner.lower()}/{package}/manifests/{digest}"
        auth = base64.b64encode(self.token.encode()).decode()
        body, _ = request("GET", url, {"Authorization": f"Bearer {auth}", "Accept": MANIFEST_TYPES})
        return [m["digest"] for m in body.get("manifests", [])]


def describe(package, v):
    return f"{package} version id={v['id']} tags={','.join(tags(v))}"


def delete_all(ghcr, package, versions, scopes, dry_run, strict):
    for v in versions:
        if dry_run:
            print(f"[dry run] Would delete {describe(package, v)}")
            continue
        try:
            ghcr.delete(package, v["id"], scopes)
            print(f"Deleted {describe(package, v)}")
        except OSError as e:
            if strict:
                raise
            print(f"::warning::Failed to delete {describe(package, v)}: {e}")


def main(mode):
    if mode not in ("pr-closed", "untagged"):
        sys.exit(f"usage: {sys.argv[0]} pr-closed|untagged")
    ghcr = Ghcr(os.environ["GITHUB_OWNER"], os.environ["GITHUB_TOKEN"])
    dry_run = os.environ.get("DRY_RUN") == "true"
    if mode == "pr-closed":
        pr = os.environ["PR_NUMBER"]
        scopes = ["orgs", "users"]
        for package in PACKAGES:
            try:
                versions = ghcr.versions(package, scopes)
            except OSError as e:
                print(f"Skipping {package}: {e}")
                continue
            doomed = closed_pr_versions(versions, pr)
            print(f"{package}: found {len(doomed)} version(s) to delete for PR #{pr}")
            delete_all(ghcr, package, doomed, scopes, dry_run, strict=True)
    else:
        min_hours = float(os.environ.get("HOURS_OLD") or 48)
        print(f"Targeting untagged and stale staging versions older than {min_hours} hours.")
        scopes = ["orgs"]
        for package in PACKAGES:
            try:
                versions = ghcr.versions(package, scopes)
            except OSError as e:
                print(f"Skipping {package}: {e}")
                continue
            print(f"{package}: {len(versions)} version(s) retrieved")
            references = {}
            for v in versions:
                if not tags(v):
                    continue
                try:
                    references[v["name"]] = ghcr.references(package, v["name"])
                except OSError as e:
                    print(f"::warning::{package}: cannot read {v['name']} ({e}); "
                          "skipping this package to avoid deleting a live image")
                    break
            doomed = deletable(versions, references, datetime.now(timezone.utc), min_hours)
            if doomed is None:
                continue
            print(f"{package}: {len(doomed)} version(s) to delete")
            delete_all(ghcr, package, doomed, scopes, dry_run, strict=False)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
