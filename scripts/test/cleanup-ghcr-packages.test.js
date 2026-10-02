// Tests for scripts/cleanup-ghcr-packages.js. Run with `node --test scripts/` (the `lint` job
// in ghci.yaml does). The fixture is one package snapshot; each digest is named after what it
// stands for, e.g. sha256:base-index is the index the `base` tag points at.

'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const c = require('../cleanup-ghcr-packages.js');
const fixture = require(path.join(__dirname, 'fixtures', 'e3sm-ghci.json'));

const SHA = '0123456789abcdef0123456789abcdef01234567';
const NOW = new Date(fixture.now);
const manifests = () => new Map(Object.entries(fixture.manifests));
const names = vs => vs.map(v => v.name.replace(/^sha256:/, '')).sort();
const version = (name, tags, created_at = '2026-09-20T00:00:00Z', id = name) =>
  ({ id, name: `sha256:${name}`, created_at, metadata: { container: { tags } } });

function sweep(versions = fixture.versions, m = manifests(), minHours = 48) {
  return c.selectDeletable(versions, m, NOW, minHours);
}

// ---- tag patterns ----

test('merge_group tags: full 40-hex sha, optional trailing arch', () => {
  assert.ok(c.MG_RE.test(`base-mg-${SHA}`));
  assert.ok(c.MG_RE.test(`buildcache-base-mg-${SHA}-x86_64`));
  assert.ok(c.MG_RE.test(`buildcache-base-mg-${SHA}-aarch64`));
  assert.ok(!c.MG_RE.test('base-mg-abc123'));
  assert.ok(!c.MG_RE.test(`base-mg-${SHA}-riscv64`));
  assert.ok(!c.MG_RE.test(`base-mg-${SHA.toUpperCase()}`));
});

test('RC_RE: -rc-<run_id> staging tags, with an optional arch', () => {
  assert.ok(c.RC_RE.test('base-rc-123456789'));
  assert.ok(c.RC_RE.test('base-dev-rc-123456789'));
  assert.ok(!c.RC_RE.test('base-rc-'));
  assert.ok(!c.RC_RE.test('base-rc-abc'));
});

test('isEphemeralMergeGroup: -rc- staging tags age out like -mg- ones, unless promoted', () => {
  const eph = tags => c.isEphemeralMergeGroup(version('x', tags));
  assert.ok(eph(['base-rc-42']));
  assert.ok(eph(['base-rc-42', `base-mg-${SHA}`]));
  // promote retags the tested digest, so the version now also carries the published tag
  assert.ok(!eph(['base-rc-42', 'base']));
  assert.ok(!eph(['base-rc-42', 'base-26.10']));
});

test('isEphemeralMergeGroup: needs an -mg- tag, and every other tag -mg- or -pr-', () => {
  const eph = tags => c.isEphemeralMergeGroup(version('x', tags));
  assert.ok(eph([`base-mg-${SHA}`]));
  assert.ok(eph([`base-mg-${SHA}`, 'base-pr-123']));
  assert.ok(eph([`buildcache-base-mg-${SHA}-x86_64`, 'buildcache-base-pr-7-x86_64']));
  assert.ok(!eph([]), 'untagged is not "ephemeral merge_group"');
  assert.ok(!eph(['base-pr-123']), '-pr-only is left to pr-closed');
  assert.ok(!eph(['base', `base-mg-${SHA}`]), 'a real tag on the same digest keeps it');
  assert.ok(!eph(['buildcache-base-x86_64']), 'a live buildcache tag is never ephemeral');
});

test('closed-PR tag pattern matches only that PR number, with optional arch', () => {
  const re = c.prTagRe(12);
  assert.ok(re.test('dev-pr-12'));
  assert.ok(re.test('buildcache-base-pr-12-aarch64'));
  assert.ok(!re.test('dev-pr-123'));
  assert.ok(!re.test('dev-pr-1'));
  assert.ok(!re.test('dev-pr-12-ppc64le'));
});

// ---- untagged mode: selectDeletable on the fixture ----

test('fixture sweep deletes exactly the stale untagged and merge_group versions', () => {
  const { toDelete } = sweep();
  assert.deepEqual(names(toDelete), ['cache-mg', 'mg-index', 'mgpr-index', 'orphan-old'].sort());
});

test('a tagged index protects its per-arch children', () => {
  const { toDelete, inUse } = sweep();
  for (const d of ['base-amd64', 'base-arm64', 'dev-amd64', 'pr99-amd64']) {
    assert.ok(inUse.has(`sha256:${d}`), d);
    assert.ok(!names(toDelete).includes(d), d);
  }
});

test('attestation manifests (unknown/unknown) are protected via the index that lists them', () => {
  const { toDelete, inUse } = sweep();
  assert.ok(inUse.has('sha256:base-amd64-att'));
  assert.ok(inUse.has('sha256:base-arm64-att'));
  assert.ok(!names(toDelete).some(n => n.endsWith('-att')));
  // ...and become deletable only once nothing tagged lists them any more.
  const m = manifests();
  m.set('sha256:base-index', ['sha256:base-amd64', 'sha256:base-arm64']);
  assert.ok(names(sweep(fixture.versions, m).toDelete).includes('base-amd64-att'));
});

test('a digest shared by a real tag and a -pr- tag is kept', () => {
  const { toDelete, inUse } = sweep();
  assert.ok(inUse.has('sha256:dev-index'));
  assert.ok(!names(toDelete).includes('dev-index'));
});

test('a digest shared by a real tag and an -mg- tag is kept', () => {
  assert.ok(!names(sweep().toDelete).includes('mgmain-index'));
});

test('an -mg- digest also tagged -pr-<N> is swept as a whole', () => {
  assert.ok(names(sweep().toDelete).includes('mgpr-index'));
});

test('a -pr-<N>-only version is never swept by age', () => {
  const names_ = names(sweep(fixture.versions, manifests(), 0).toDelete);
  assert.ok(!names_.includes('pr99-index'));
  assert.ok(!names_.includes('cache-pr'));
});

test('a live buildcache-* tag is never deleted, however old, and protects its cache blobs', () => {
  const { toDelete, inUse } = sweep(fixture.versions, manifests(), 0);
  assert.ok(!names(toDelete).includes('cache-index'));
  assert.ok(inUse.has('sha256:cache-blob'));
  assert.ok(!names(toDelete).includes('cache-blob'));
});

test('a superseded buildcache digest (now untagged, unreferenced) is swept', () => {
  const versions = [version('cache-new', ['buildcache-base-x86_64']), version('cache-old', [])];
  const m = new Map([['sha256:cache-new', []]]);
  assert.deepEqual(names(sweep(versions, m).toDelete), ['cache-old']);
});

test('-mg-<sha> versions are swept only when older than minHours', () => {
  const { toDelete } = sweep();
  assert.ok(names(toDelete).includes('mg-index'));
  assert.ok(names(toDelete).includes('cache-mg'));
  assert.ok(!names(toDelete).includes('mg-young'), '12h old < 48h');
  assert.ok(names(sweep(fixture.versions, manifests(), 6).toDelete).includes('mg-young'));
});

test('an -mg- tag without a full sha is not treated as ephemeral', () => {
  assert.ok(!names(sweep(fixture.versions, manifests(), 0).toDelete).includes('mg-short'));
});

test('age threshold is strict: exactly minHours old is kept', () => {
  const { toDelete } = sweep();
  assert.ok(!names(toDelete).includes('orphan-exact'));
  assert.ok(!names(toDelete).includes('orphan-young'));
  assert.ok(names(sweep(fixture.versions, manifests(), 47.9).toDelete).includes('orphan-exact'));
});

test('a NaN minHours (non-numeric input) deletes nothing', () => {
  assert.deepEqual(sweep(fixture.versions, manifests(), NaN).toDelete, []);
});

test("a swept -mg- index's children survive this run and are swept on the next", () => {
  const first = sweep();
  assert.ok(names(first.toDelete).includes('mg-index'));
  assert.ok(first.inUse.has('sha256:mg-amd64'));
  assert.ok(!names(first.toDelete).includes('mg-amd64'));
  const deleted = new Set(first.toDelete.map(v => v.name));
  const after = fixture.versions.filter(v => !deleted.has(v.name));
  assert.ok(names(sweep(after).toDelete).includes('mg-amd64'));
});

test('failed manifest read => nothing is deleted (fail safe)', () => {
  const m = manifests();
  m.delete('sha256:dev-index');
  assert.deepEqual(sweep(fixture.versions, m), { unresolved: 'sha256:dev-index' });
  // Even for an unresolvable *sweepable* version: its references are unknown too.
  const m2 = manifests();
  m2.delete('sha256:mg-index');
  assert.deepEqual(sweep(fixture.versions, m2), { unresolved: 'sha256:mg-index' });
});

test('nested index: only one level of references is followed (current behaviour)', () => {
  // Nothing this repo pushes nests indexes. This pins today's behaviour so that changing it
  // (following references recursively) is a deliberate, visible decision.
  const versions = [
    version('outer', ['nested']),
    version('inner', []),
    version('leaf', []),
  ];
  const m = new Map([['sha256:outer', ['sha256:inner']]]);
  const { toDelete, inUse } = sweep(versions, m);
  assert.ok(inUse.has('sha256:inner'));
  assert.ok(!inUse.has('sha256:leaf'));
  assert.deepEqual(names(toDelete), ['leaf']);
});

test('referencedDigests reads an index and treats an image manifest as a leaf', () => {
  assert.deepEqual(
    c.referencedDigests({ manifests: [{ digest: 'sha256:a', platform: { os: 'unknown', architecture: 'unknown' } }, { digest: 'sha256:b' }] }),
    ['sha256:a', 'sha256:b'],
  );
  assert.deepEqual(c.referencedDigests({ config: {}, layers: [] }), []);
});

test('parseHours: unset/empty -> 48, otherwise parseFloat', () => {
  assert.equal(c.parseHours(undefined), 48);
  assert.equal(c.parseHours(''), 48);
  assert.equal(c.parseHours('12.5'), 12.5);
  assert.ok(Number.isNaN(c.parseHours('soon')));
});

// ---- pr-closed mode ----

test('pr-closed deletes versions whose every tag is that PR, arch-suffixed or not', () => {
  const versions = [
    ...fixture.versions,
    version('pr12-only', ['dev-pr-12', 'base-pr-12']),
    version('pr12-cache', ['buildcache-dev-pr-12-x86_64']),
  ];
  assert.deepEqual(names(c.selectClosedPrVersions(versions, 12)), ['cache-pr', 'pr12-cache', 'pr12-only']);
  // dev-index carries `dev` too, so closing PR 12 must not take main's tag down with it.
  assert.ok(!names(c.selectClosedPrVersions(versions, 12)).includes('dev-index'));
  // Untagged versions and other PRs' tags are never touched.
  assert.deepEqual(names(c.selectClosedPrVersions(fixture.versions, 99)), ['pr99-index']);
  assert.deepEqual(c.selectClosedPrVersions(fixture.versions, 1), []);
});

// ---- per-package runs with a fake API ----

function fakeApi({ versions = fixture.versions, manifests: m = fixture.manifests, failManifest, failList, failDelete } = {}) {
  const calls = { deleted: [], manifestReads: [], list: [] };
  return {
    calls,
    async listVersions(pkg, opts) {
      calls.list.push(opts);
      if (failList) throw new Error('boom');
      return versions;
    },
    async readManifestRefs(pkg, digest) {
      calls.manifestReads.push(digest);
      if (digest === failManifest) throw new Error(`manifest ${digest} -> HTTP 500`);
      return m[digest];
    },
    async deleteVersion(pkg, id, opts) {
      if (failDelete && failDelete(id)) throw new Error(`cannot delete ${id}`);
      calls.deleted.push({ id, opts });
    },
  };
}

function fakeLog() {
  const lines = [];
  return { lines, info: s => lines.push(`info: ${s}`), warning: s => lines.push(`warning: ${s}`) };
}

const untaggedRun = (api, log, extra = {}) => c.cleanupUntagged({
  pkg: 'e3sm-ghci', api, log, now: NOW, minHours: 48, dryRun: false, isSweepable: c.isEphemeralMergeGroup, ...extra,
});

test('untagged run deletes the selection via /orgs only and logs as before', async () => {
  const api = fakeApi();
  const log = fakeLog();
  await untaggedRun(api, log);
  const ids = n => fixture.versions.find(v => v.name === `sha256:${n}`).id;
  assert.deepEqual(api.calls.deleted.map(d => d.id).sort((a, b) => a - b),
    ['mg-index', 'mgpr-index', 'cache-mg', 'orphan-old'].map(ids).sort((a, b) => a - b));
  assert.ok(api.calls.deleted.every(d => d.opts.userFallback === false));
  assert.deepEqual(api.calls.list, [{ userFallback: false }]);
  assert.ok(log.lines.includes(`info: e3sm-ghci: ${fixture.versions.length} version(s) retrieved`));
  assert.ok(log.lines.some(l => /^info: e3sm-ghci: 4 version\(s\) match \(untagged or merge_group\), \d+ digest\(s\) in use$/.test(l)));
  assert.ok(log.lines.includes(`info: Deleted e3sm-ghci version id=${ids('mgpr-index')} tags=base-mg-${SHA},base-pr-123`));
});

test('untagged run: a failed manifest read stops reading and deletes nothing', async () => {
  const api = fakeApi({ failManifest: 'sha256:dev-index' });
  const log = fakeLog();
  assert.deepEqual(await untaggedRun(api, log), []);
  assert.deepEqual(api.calls.deleted, []);
  assert.equal(api.calls.manifestReads.at(-1), 'sha256:dev-index');
  assert.ok(log.lines.includes('warning: e3sm-ghci: cannot resolve sha256:dev-index (manifest sha256:dev-index -> HTTP 500); skipping this package to avoid deleting a live image'));
});

test('untagged run: a failed listing skips the package', async () => {
  const api = fakeApi({ failList: true });
  const log = fakeLog();
  assert.deepEqual(await untaggedRun(api, log), []);
  assert.deepEqual(log.lines, ['info: Skipping e3sm-ghci: boom']);
});

test('untagged run: a failed delete warns and carries on', async () => {
  const first = fixture.versions.find(v => v.name === 'sha256:mg-index').id;
  const api = fakeApi({ failDelete: id => id === first });
  const log = fakeLog();
  await untaggedRun(api, log);
  assert.equal(api.calls.deleted.length, 3);
  assert.ok(log.lines.includes(`warning: Failed to delete e3sm-ghci version id=${first}: cannot delete ${first}`));
});

test('untagged run: dry run deletes nothing and says what it would delete', async () => {
  const api = fakeApi();
  const log = fakeLog();
  const selected = await untaggedRun(api, log, { dryRun: true });
  assert.equal(selected.length, 4);
  assert.deepEqual(api.calls.deleted, []);
  assert.equal(log.lines.filter(l => l.startsWith('info: [dry run] Would delete e3sm-ghci version id=')).length, 4);
});

test('pr-closed run deletes with the /users fallback and fails loudly on a delete error', async () => {
  const api = fakeApi();
  const log = fakeLog();
  await c.cleanupClosedPr({ pkg: 'e3sm-ghci', pr: 99, api, log, dryRun: false });
  assert.deepEqual(api.calls.list, [{ userFallback: true }]);
  assert.deepEqual(api.calls.deleted.map(d => d.opts), [{ userFallback: true }]);
  assert.ok(log.lines.includes('info: e3sm-ghci: found 1 version(s) to delete for PR #99'));

  const bad = fakeApi({ failDelete: () => true });
  await assert.rejects(c.cleanupClosedPr({ pkg: 'e3sm-ghci', pr: 99, api: bad, log: fakeLog(), dryRun: false }));
});

test('pr-closed run: dry run deletes nothing', async () => {
  const api = fakeApi();
  const log = fakeLog();
  await c.cleanupClosedPr({ pkg: 'e3sm-ghci', pr: 12, api, log, dryRun: true });
  assert.deepEqual(api.calls.deleted, []);
  assert.ok(log.lines.some(l => l.startsWith('info: [dry run] Would delete e3sm-ghci version id=')));
});

// ---- main(): package table and policies ----

test('the package table covers e3sm-ghci with the default policy', () => {
  assert.equal(c.PACKAGES['e3sm-ghci'], c.DEFAULT_POLICY);
});

test('main honours per-package policies (NEVER_CLEAN is never listed or deleted)', async () => {
  const api = fakeApi();
  const log = fakeLog();
  const packages = { 'e3sm-ghci': c.DEFAULT_POLICY, 'spack-cache': c.NEVER_CLEAN };
  await c.main(['untagged'], { HOURS_OLD: '' }, log, { packages, api });
  await c.main(['pr-closed'], { PR_NUMBER: '99' }, log, { packages, api });
  assert.equal(api.calls.list.length, 2, 'only e3sm-ghci is listed, once per mode');
  assert.ok(log.lines.includes('info: Targeting untagged images and merge_group -mg-<sha> images older than 48 hours.'));
  assert.ok(log.lines.includes('info: Skipping spack-cache: never swept by age'));
  assert.ok(log.lines.includes('info: Skipping spack-cache: never cleaned on PR close'));
});

test('a BuildKit cache package keeps <tag>-<arch> and expires -pr-/-mg- suffixed tags under DEFAULT_POLICY', async () => {
  // What adding e3sm-ghci-buildcache with DEFAULT_POLICY would do.
  const versions = [
    version('live', ['base-x86_64']),
    version('mg', [`base-mg-${SHA}-aarch64`]),
    version('pr', ['base-pr-7-x86_64']),
  ];
  const m = new Map(versions.map(v => [v.name, []]));
  assert.deepEqual(names(sweep(versions, m, 0).toDelete), ['mg']);
  assert.deepEqual(names(c.selectClosedPrVersions(versions, 7)), ['pr']);
});

test('main rejects an unknown mode and missing settings', async () => {
  await assert.rejects(c.main(['everything'], {}, fakeLog(), { api: fakeApi() }), /usage/);
  await assert.rejects(c.main(['pr-closed'], {}, fakeLog(), { api: fakeApi() }), /PR_NUMBER is not set/);
  await assert.rejects(c.main(['untagged'], {}, fakeLog()), /GITHUB_TOKEN is not set/);
});

// ---- I/O layer against a fake fetch ----

function fakeFetch(routes) {
  const seen = [];
  const impl = async (url, init = {}) => {
    seen.push({ url, method: init.method || 'GET', headers: init.headers });
    const r = routes(url, init.method || 'GET');
    return {
      ok: r.status >= 200 && r.status < 300,
      status: r.status,
      headers: new Map(Object.entries(r.headers || {})),
      json: async () => r.body,
    };
  };
  return { impl, seen };
}

test('listVersions follows Link pagination', async () => {
  const base = 'https://api.example/orgs/E3SM-Project/packages/container/e3sm-ghci/versions';
  const { impl, seen } = fakeFetch(url => (url.endsWith('per_page=100')
    ? { status: 200, body: [{ id: 1 }], headers: { link: `<${base}?per_page=100&page=2>; rel="next", <${base}?page=2>; rel="last"` } }
    : { status: 200, body: [{ id: 2 }] }));
  const api = c.makeApi({ token: 't', owner: 'E3SM-Project', apiUrl: 'https://api.example', fetchImpl: impl });
  assert.deepEqual(await api.listVersions('e3sm-ghci', { userFallback: false }), [{ id: 1 }, { id: 2 }]);
  assert.equal(seen.length, 2);
  assert.equal(seen[0].headers.Authorization, 'Bearer t');
});

test('listVersions/deleteVersion fall back from /orgs to /users only when asked', async () => {
  const routes = url => (url.includes('/orgs/') ? { status: 404, body: { message: 'Not Found' } } : { status: 200, body: [] });
  let f = fakeFetch(routes);
  let api = c.makeApi({ token: 't', owner: 'me', apiUrl: 'https://api.example', fetchImpl: f.impl });
  assert.deepEqual(await api.listVersions('p', { userFallback: true }), []);
  await api.deleteVersion('p', 5, { userFallback: true });
  assert.deepEqual(f.seen.map(s => `${s.method} ${s.url.split('/')[3]}`),
    ['GET orgs', 'GET users', 'DELETE orgs', 'DELETE users']);

  f = fakeFetch(routes);
  api = c.makeApi({ token: 't', owner: 'me', apiUrl: 'https://api.example', fetchImpl: f.impl });
  await assert.rejects(api.listVersions('p', { userFallback: false }), /HTTP 404: Not Found/);
  await assert.rejects(api.deleteVersion('p', 5, { userFallback: false }), /HTTP 404/);
  assert.equal(f.seen.length, 2);
});

test('readManifestRefs: lower-cased owner, base64 token, OCI/Docker accept, throws on HTTP error', async () => {
  const { impl, seen } = fakeFetch(url => (url.endsWith('sha256:bad')
    ? { status: 401 }
    : { status: 200, body: { manifests: [{ digest: 'sha256:a' }] } }));
  const api = c.makeApi({ token: 'tok', owner: 'E3SM-Project', fetchImpl: impl });
  assert.deepEqual(await api.readManifestRefs('e3sm-ghci', 'sha256:x'), ['sha256:a']);
  assert.equal(seen[0].url, 'https://ghcr.io/v2/e3sm-project/e3sm-ghci/manifests/sha256:x');
  assert.equal(seen[0].headers.Authorization, `Bearer ${Buffer.from('tok').toString('base64')}`);
  assert.match(seen[0].headers.Accept, /application\/vnd\.oci\.image\.index\.v1\+json/);
  assert.match(seen[0].headers.Accept, /application\/vnd\.docker\.distribution\.manifest\.list\.v2\+json/);
  await assert.rejects(api.readManifestRefs('e3sm-ghci', 'sha256:bad'), /manifest sha256:bad -> HTTP 401/);
});

test('nextLink parses only rel="next"', () => {
  assert.equal(c.nextLink('<https://x/?page=3>; rel="next", <https://x/?page=9>; rel="last"'), 'https://x/?page=3');
  assert.equal(c.nextLink('<https://x/?page=1>; rel="prev"'), undefined);
  assert.equal(c.nextLink(null), undefined);
});
