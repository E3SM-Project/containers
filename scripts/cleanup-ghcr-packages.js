#!/usr/bin/env node
// Deletes stale GHCR package versions for .github/workflows/cleanup-ghcr-packages.yaml.
//
// This is the one piece of automation in the repo that deletes things, so the decision of
// *what* to delete lives in pure functions below (tested by scripts/test/, run in the `lint`
// job of ghci.yaml) and the REST/registry calls are kept in a thin I/O layer at the bottom.
// Plain Node (>= 18, for the global fetch), no npm dependencies, so the workflow can run it
// straight from a checkout with `node scripts/cleanup-ghcr-packages.js <mode>`.
//
// Modes:
//   pr-closed   delete the versions a just-closed PR published (job delete-pr-images)
//   untagged    age out untagged and merge_group versions (job cleanup-untagged)
//
// Environment:
//   GITHUB_TOKEN       token for the REST API and the ghcr.io registry (packages: write)
//   GITHUB_OWNER       org (or user) owning the packages
//   PR_NUMBER          pr-closed: number of the PR that was closed
//   HOURS_OLD          untagged: minimum age in hours; empty/unset means the default (48)
//   DRY_RUN            'true' logs what would be deleted without deleting anything
//   GITHUB_API_URL     REST API base (set by Actions; defaults to https://api.github.com)

'use strict';

const ARCH = '(?:-(?:x86_64|aarch64))?';

// merge_group runs publish under an ephemeral <tag>-mg-<sha> tag (see build-multiarch.yaml)
// so that stage-to-stage chaining works within that one validation run; there is no single
// PR to key cleanup on the way pr-closed does (a merge_group run can batch several PRs), so
// these age out in the untagged mode instead, same as genuinely untagged versions.
//
// build-multiarch.yaml also scopes a PR/merge_group run's own cache-to writes to
// buildcache-<tag>-pr-<N>-<arch> / buildcache-<tag>-mg-<sha>-<arch> (see its tag_suffix
// input), so both patterns accept an optional trailing arch too, on top of the plain image
// tags.
const MG_RE = new RegExp(`-mg-[0-9a-f]{40}${ARCH}$`);
const PR_RE = new RegExp(`-pr-\\d+${ARCH}$`);

// The tags of one package version (the REST API's `metadata.container.tags`).
const tagsOf = v => v.metadata?.container?.tags || [];

// Tags a closed PR #<pr> published, with the same optional trailing arch as above.
const prTagRe = pr => new RegExp(`-pr-${pr}${ARCH}$`);

// A merge_group build can be byte-identical to a same-PR pull_request build (a stage the PR
// didn't touch), in which case GHCR attaches BOTH tags to the one shared version -- e.g.
// ["base-pr-123", "base-mg-<sha>"]. pr-closed (which only fires for its own closing PR's
// number) and a pure -mg-only check both conservatively refuse to touch a version unless
// every tag matches their own pattern, so a version like that would never qualify for
// either and would sit there forever. Once at least one tag is -mg-*, treat every other
// -pr-<N>-only tag alongside it as equally ephemeral too -- but only then: a version tagged
// solely -pr-<N> (no -mg- tag at all, e.g. a still-open PR nobody has re-pushed in a while)
// is intentionally left alone by the age sweep; pr-closed remains the only thing that ever
// removes those, on PR close.
function isEphemeralMergeGroup(v) {
  const t = tagsOf(v);
  return t.length > 0 && t.some(x => MG_RE.test(x)) && t.every(x => MG_RE.test(x) || PR_RE.test(x));
}

// buildcache-* tags are never swept by age while still live. An earlier version of this job
// deleted the *current* buildcache-<tag>-<arch> pointer once it turned 48h old, reasoning it
// was an orphaned tag from a stage/arch combo no longer built -- but base/compiler layers
// routinely go longer than that between rebuilds, so it was really deleting the only cache
// build-multiarch.yaml had for that stage/arch, forcing the next PR touching anything
// downstream into a fully cold build. A buildcache tag only ever points at one digest at a
// time, so once a fresh `cache-to` moves it to a new digest, the superseded digest becomes
// genuinely untagged and is swept by the ordinary untagged-version case -- no age check
// keyed on the tag name is needed for that case. A stage/arch combo that stops being built
// entirely keeps its buildcache tag (and the blobs it references) around indefinitely; on a
// public package that costs nothing. None of that needs a buildcache-specific rule: a plain
// buildcache-<tag>-<arch> tag simply never matches isEphemeralMergeGroup.

// Per-package cleanup policy:
//   deleteOnPrClose  pr-closed deletes versions whose every tag is -pr-<N>[-<arch>]
//   sweepByAge       untagged sweeps old untagged versions and versions isSweepable accepts
//   isSweepable      which *tagged* versions the age sweep may delete; every other tagged
//                    version is kept, and protects whatever its manifest references
const DEFAULT_POLICY = Object.freeze({
  deleteOnPrClose: true,
  sweepByAge: true,
  isSweepable: isEphemeralMergeGroup,
});

// Never touched by either mode (still listed, so the log says why it was skipped).
const NEVER_CLEAN = Object.freeze({ deleteOnPrClose: false, sweepByAge: false, isSweepable: () => false });

// Every package this repo publishes. Keep in sync with the workflows that push to GHCR.
//
// Adding a package is one entry here. DEFAULT_POLICY already keeps every tag that isn't
// ephemeral, so a BuildKit registry cache package such as e3sm-ghci-buildcache needs nothing
// special: its plain <tag>-<arch> cache tags are kept like buildcache-* tags are above, and
// its suffixed <tag>-pr-<N>-<arch> / <tag>-mg-<sha>-<arch> tags are expired by the same
// rules as here:
//   'e3sm-ghci-buildcache': DEFAULT_POLICY,
// A package that must never be cleaned (e.g. the Spack OCI binary cache, which spack itself
// manages and whose layout these image-oriented rules know nothing about) opts out entirely:
//   'e3sm-spack-buildcache': NEVER_CLEAN,
// Anything in between is a new policy object with its own isSweepable (plus a test).
const PACKAGES = Object.freeze({
  'e3sm-ghci': DEFAULT_POLICY,
  // BuildKit registry cache (build-multiarch.yaml's CACHE)
  'e3sm-ghci-buildcache': DEFAULT_POLICY,
});

// pr-closed: the versions to delete for closed PR #<pr>.
//
// A version can carry several tags: a fully cached PR build is byte-identical to main's, so
// one digest may hold both `base` and `base-pr-N`. Deleting it would take the main tag down
// too, so only delete versions no other tag still points at.
function selectClosedPrVersions(versions, pr) {
  const re = prTagRe(pr);
  return versions.filter(v => {
    const t = tagsOf(v);
    return t.length > 0 && t.every(x => re.test(x));
  });
}

// untagged: the versions to delete by age.
//
//   versions   the package's versions from the REST API
//   manifests  Map of tagged digest -> digests its manifest references ([] for a plain image
//              manifest); a tagged digest missing from it is one whose manifest could not be
//              read
//   now        Date
//   minHours   only versions strictly older than this are deleted
//
// Returns { toDelete, inUse } or, if any tagged manifest is unresolved, { unresolved: digest }
// -- not knowing what a tag references means not knowing what is safe, so delete nothing.
function selectDeletable(versions, manifests, now, minHours, isSweepable = DEFAULT_POLICY.isSweepable) {
  const tagged = versions.filter(v => tagsOf(v).length > 0);
  // The per-arch images a multi-arch tag points at (and its attestation manifests, the
  // platform unknown/unknown entries buildx adds to the same index) are themselves UNTAGGED
  // package versions, so deleting untagged versions by age would break every multi-arch tag.
  // Every tagged manifest's references are therefore in use.
  //
  // A sweepable (mg-only/mg+pr) version is never the digest a real published tag's manifest
  // list points at, so it doesn't need to protect anything by being marked in-use. A live
  // buildcache-* tag is never sweepable, so its own digest lands in `inUse` here too; it isn't
  // pushed with image-manifest=true, so it can itself be an OCI index referencing several
  // untagged config/layer blobs used for cache import -- those get protected the same way.
  //
  // Only one level is followed: a tagged index's children are protected, not grandchildren
  // of a nested index. Nothing this repo pushes nests indexes.
  const inUse = new Set(tagged.filter(v => !isSweepable(v)).map(v => v.name));
  for (const v of tagged) {
    const refs = manifests.get(v.name);
    if (!refs) return { unresolved: v.name };
    for (const d of refs) inUse.add(d);
  }
  const toDelete = versions.filter(v => {
    if (tagsOf(v).length > 0 && !isSweepable(v)) return false;
    if (inUse.has(v.name)) return false;
    return (now - new Date(v.created_at)) / 36e5 > minHours;
  });
  return { toDelete, inUse };
}

// The digests an image index / manifest list references (none for a single image manifest).
const referencedDigests = body => (body.manifests || []).map(m => m.digest);

// HOURS_OLD as the workflow passes it: unset/empty (schedule) -> 48, otherwise parseFloat.
// A non-numeric value yields NaN, which no age exceeds, so nothing is deleted.
const parseHours = s => (s === undefined || s === '' ? 48 : parseFloat(s));

const formatDeleted = (pkg, v) => `${pkg} version id=${v.id} tags=${tagsOf(v).join(',')}`;

// ---- per-package runs (I/O injected via `api` and `log`, so tests can fake them) ----

async function cleanupClosedPr({ pkg, pr, api, log, dryRun }) {
  let versions;
  try {
    versions = await api.listVersions(pkg, { userFallback: true });
  } catch (e) {
    log.info(`Skipping ${pkg}: ${e.message}`);
    return [];
  }
  const toDelete = selectClosedPrVersions(versions, pr);
  log.info(`${pkg}: found ${toDelete.length} version(s) to delete for PR #${pr}`);
  for (const v of toDelete) {
    if (dryRun) {
      log.info(`[dry run] Would delete ${formatDeleted(pkg, v)}`);
      continue;
    }
    // A failed delete fails the job here (unlike the age sweep): a PR's images not going
    // away on close is something to notice, and nothing later retries it.
    await api.deleteVersion(pkg, v.id, { userFallback: true });
    log.info(`Deleted ${formatDeleted(pkg, v)}`);
  }
  return toDelete;
}

async function cleanupUntagged({ pkg, api, log, now, minHours, dryRun, isSweepable }) {
  let versions;
  try {
    versions = await api.listVersions(pkg, { userFallback: false });
  } catch (e) {
    log.info(`Skipping ${pkg}: ${e.message}`);
    return [];
  }
  log.info(`${pkg}: ${versions.length} version(s) retrieved`);

  // Read tagged manifests in order and stop at the first failure; selectDeletable then sees
  // that digest missing and refuses to delete anything.
  const manifests = new Map();
  let failure;
  for (const v of versions.filter(x => tagsOf(x).length > 0)) {
    try {
      manifests.set(v.name, await api.readManifestRefs(pkg, v.name));
    } catch (e) {
      failure = e;
      break;
    }
  }
  const result = selectDeletable(versions, manifests, now, minHours, isSweepable);
  if (result.unresolved) {
    const why = failure ? failure.message : 'unresolved';
    log.warning(`${pkg}: cannot resolve ${result.unresolved} (${why}); skipping this package to avoid deleting a live image`);
    return [];
  }
  const { toDelete, inUse } = result;
  log.info(`${pkg}: ${toDelete.length} version(s) match (untagged or merge_group), ${inUse.size} digest(s) in use`);

  for (const v of toDelete) {
    if (dryRun) {
      log.info(`[dry run] Would delete ${formatDeleted(pkg, v)}`);
      continue;
    }
    try {
      await api.deleteVersion(pkg, v.id, { userFallback: false });
      log.info(`Deleted ${formatDeleted(pkg, v)}`);
    } catch (e) {
      log.warning(`Failed to delete ${pkg} version id=${v.id}: ${e.message}`);
    }
  }
  return toDelete;
}

// ---- thin I/O layer: GitHub REST API and the ghcr.io registry ----

const MANIFEST_ACCEPT = [
  'application/vnd.oci.image.index.v1+json',
  'application/vnd.docker.distribution.manifest.list.v2+json',
  'application/vnd.oci.image.manifest.v1+json',
  'application/vnd.docker.distribution.manifest.v2+json',
].join(',');

// The rel="next" URL of a GitHub Link header, or undefined.
function nextLink(header) {
  const m = /<([^>]+)>;\s*rel="next"/.exec(header || '');
  return m ? m[1] : undefined;
}

function makeApi({ token, owner, apiUrl = 'https://api.github.com', fetchImpl = fetch }) {
  const headers = {
    Accept: 'application/vnd.github+json',
    Authorization: `Bearer ${token}`,
    'X-GitHub-Api-Version': '2022-11-28',
    'User-Agent': 'e3sm-containers-cleanup',
  };
  async function request(method, url) {
    const res = await fetchImpl(url, { method, headers });
    if (!res.ok) {
      let detail = '';
      try { detail = `: ${(await res.json()).message}`; } catch { /* no JSON body */ }
      throw new Error(`${method} ${url} -> HTTP ${res.status}${detail}`);
    }
    return res;
  }
  // Container packages live under /orgs for an org and /users for a personal account; the
  // pr-closed mode has always tried both, the untagged mode only /orgs.
  const scopes = userFallback => (userFallback ? ['orgs', 'users'] : ['orgs']);
  const versionsPath = (scope, pkg) =>
    `${apiUrl}/${scope}/${encodeURIComponent(owner)}/packages/container/${encodeURIComponent(pkg)}/versions`;

  return {
    async listVersions(pkg, { userFallback }) {
      let lastError;
      for (const scope of scopes(userFallback)) {
        try {
          const versions = [];
          let url = `${versionsPath(scope, pkg)}?per_page=100`;
          while (url) {
            const res = await request('GET', url);
            versions.push(...(await res.json()));
            url = nextLink(res.headers.get('link'));
          }
          return versions;
        } catch (e) {
          lastError = e;
        }
      }
      throw lastError;
    },
    async deleteVersion(pkg, id, { userFallback }) {
      const [first, second] = scopes(userFallback);
      try {
        await request('DELETE', `${versionsPath(first, pkg)}/${id}`);
      } catch (e) {
        if (!second) throw e;
        await request('DELETE', `${versionsPath(second, pkg)}/${id}`);
      }
    },
    async readManifestRefs(pkg, digest) {
      // ghcr.io accepts the GitHub token itself, base64-encoded, as a registry bearer token.
      const url = `https://ghcr.io/v2/${owner.toLowerCase()}/${pkg}/manifests/${digest}`;
      const res = await fetchImpl(url, {
        headers: { Authorization: `Bearer ${Buffer.from(token).toString('base64')}`, Accept: MANIFEST_ACCEPT },
      });
      if (!res.ok) {
        // Cannot read the manifest -> do not know what it references -> delete nothing
        throw new Error(`manifest ${digest} -> HTTP ${res.status}`);
      }
      return referencedDigests(await res.json());
    },
  };
}

// Workflow-command escaping, as @actions/core does, so a message can't end the annotation.
const escapeCommand = s => String(s).replace(/%/g, '%25').replace(/\r/g, '%0D').replace(/\n/g, '%0A');
const actionsLog = {
  info: msg => console.log(msg),
  warning: msg => console.log(`::warning::${escapeCommand(msg)}`),
};

// `packages` and `api` are injectable for the tests; the workflow uses the defaults.
async function main(argv = process.argv.slice(2), env = process.env, log = actionsLog, { packages = PACKAGES, api } = {}) {
  const mode = argv[0];
  const required = name => {
    if (!env[name]) throw new Error(`${name} is not set`);
    return env[name];
  };
  api = api || makeApi({
    token: required('GITHUB_TOKEN'),
    owner: required('GITHUB_OWNER'),
    apiUrl: env.GITHUB_API_URL || undefined,
  });
  const dryRun = env.DRY_RUN === 'true';
  if (dryRun) log.info('Dry run: nothing will be deleted.');

  if (mode === 'pr-closed') {
    const pr = required('PR_NUMBER');
    for (const [pkg, policy] of Object.entries(packages)) {
      if (!policy.deleteOnPrClose) {
        log.info(`Skipping ${pkg}: never cleaned on PR close`);
        continue;
      }
      await cleanupClosedPr({ pkg, pr, api, log, dryRun });
    }
  } else if (mode === 'untagged') {
    const minHours = parseHours(env.HOURS_OLD);
    log.info(`Targeting untagged images and merge_group -mg-<sha> images older than ${minHours} hours.`);
    for (const [pkg, policy] of Object.entries(packages)) {
      if (!policy.sweepByAge) {
        log.info(`Skipping ${pkg}: never swept by age`);
        continue;
      }
      await cleanupUntagged({ pkg, api, log, now: new Date(), minHours, dryRun, isSweepable: policy.isSweepable });
    }
  } else {
    throw new Error(`usage: cleanup-ghcr-packages.js pr-closed|untagged (got ${mode})`);
  }
}

module.exports = {
  MG_RE,
  PR_RE,
  DEFAULT_POLICY,
  NEVER_CLEAN,
  PACKAGES,
  tagsOf,
  prTagRe,
  isEphemeralMergeGroup,
  selectClosedPrVersions,
  selectDeletable,
  referencedDigests,
  parseHours,
  nextLink,
  makeApi,
  cleanupClosedPr,
  cleanupUntagged,
  main,
};

if (require.main === module) {
  main().catch(e => {
    console.log(`::error::${escapeCommand(e.message)}`);
    process.exitCode = 1;
  });
}
