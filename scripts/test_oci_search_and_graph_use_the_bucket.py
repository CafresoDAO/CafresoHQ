#!/usr/bin/env python3
"""/vault/search and /vault/graph only knew two vault backends: 'rest', and
everything else treated as 'fs'.

    if _vault_backend == 'rest':
        ...
    root = pathlib.Path(_vault_root).resolve()   # search
    ...
    graph = _build_graph_rest() if _vault_backend == 'rest' else _build_graph_fs_cached()

List, read, write and delete all branch three ways — 'rest', 'oci', 'fs' —
because those are the doors a boss actually files through. Search and the
Graph never got the third row. An OCI-backed fleet office (the deployment
CAFRESOHQ_FLEET_MODE / OCI_VAULT_NAMESPACE + OCI_VAULT_BUCKET provision) has
every note living in the bucket and nothing meaningful in `_vault_root` —
that's still a real local path (CAFRESOHQ_VAULT defaults even when unset),
so neither door crashed. Search silently searched an empty or unrelated
local directory and reported "no results" for notes that were really
sitting in the bucket. The Graph did the same and drew an empty or wrong
map. Both looked like ordinary, honest "nothing here" answers.

Root cause and fix, mirrored across both doors:

  * `/vault/search` gained an explicit `if _vault_backend == 'oci':` arm —
    `serve._oci_vault_search()` — that lists the bucket, fetches each
    text-like object, and scores it with the exact same `_vault_search_hit`
    helper the fs arm uses (factored out so the two can't drift the way
    the OCI-delete ticket's copy-by-hand `except` blocks did).

  * `/vault/graph` gained an explicit `elif _vault_backend == 'oci':` arm —
    `kg_builder._build_graph_oci_cached()`. `_build_graph_fs`'s parsing
    logic (wikilinks, tags, typed edges, the HQ-state overlay) was pulled
    out into `_build_graph_from_raw(raw)`, a shared function that takes a
    plain list of (rel, title, text, mtime, size) tuples — so `oci` gets
    the identical extraction fs already has, not a second hand-written
    copy. A signature cache (list_objects metadata only, no content
    fetched) mirrors the fs cache's mtime+size approach.

Run: python3 scripts/test_oci_search_and_graph_use_the_bucket.py
"""
import datetime
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
SERVE_RAW = (ROOT / 'serve.py').read_text(encoding='utf-8')
KG_RAW = (ROOT / 'kg_builder.py').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


# ── a fake OCI Object Storage client — no account, no network ──────────────
class _FakeObj:
    def __init__(self, name, size=0, tm=None):
        self.name = name
        self.size = size
        self.time_modified = tm or datetime.datetime(2024, 1, 1)


class _FakeData:
    def __init__(self, objects=None, content=None):
        self.objects = objects
        self.content = content


class _FakeResp:
    def __init__(self, data):
        self.data = data


class FakeOciClient:
    """Enough of oci.object_storage.ObjectStorageClient to drive
    _oci_vault_search / _build_graph_oci without the `oci` package or a
    real bucket. `contents` keys are FULL object names (prefix included),
    matching what list_objects/get_object actually receive."""
    def __init__(self, names, contents):
        self.names = names
        self.contents = contents

    def list_objects(self, namespace, bucket, prefix='', fields='', limit=1000):
        return _FakeResp(_FakeData(objects=[_FakeObj(n) for n in self.names]))

    def get_object(self, namespace, bucket, key):
        return _FakeResp(_FakeData(content=self.contents[key]))


def main():
    print('OCI backend: search and the Graph read the bucket, not _vault_root')

    # ── 1. the dispatch, read out of the source ──────────────────────────
    search_a = SERVE_RAW.index("if path == '/vault/search' and method == 'GET':")
    search_b = SERVE_RAW.index('# ---------- Graph', search_a)
    search_handler = SERVE_RAW[search_a:search_b]
    check("/vault/search names 'oci' explicitly, not just 'rest'",
          "_vault_backend == 'oci'" in search_handler,
          'this used to fall through to the fs walk for every backend that '
          "wasn't 'rest' by name")
    oci_at = search_handler.index("_vault_backend == 'oci':")
    fs_fallthrough_at = search_handler.index('root = pathlib.Path(_vault_root).resolve()')
    check('...and calls the OCI search function before the fs walk',
          oci_at < fs_fallthrough_at
          and '_oci_vault_search(' in search_handler[oci_at:fs_fallthrough_at],
          'the oci branch has to come before the plain fs code, or oci '
          'still falls through to it')
    check('fs and oci search share one scoring function (no drift)',
          search_handler.count('_vault_search_hit(') >= 1
          and 'def _vault_search_hit' not in search_handler,
          '— _vault_search_hit is defined once, above the handler; two '
          'independent copies of the scoring/snippet logic is how they '
          'drift apart later')

    graph_a = SERVE_RAW.index("if path == '/vault/graph' and method == 'GET':")
    graph_b = SERVE_RAW.index('# ---------- Open in Obsidian', graph_a)
    graph_handler = SERVE_RAW[graph_a:graph_b]
    check("/vault/graph names 'oci' explicitly",
          "_vault_backend == 'oci'" in graph_handler,
          'this used to be a two-way `rest` / else-assume-fs ternary')
    check('...and builds it from the bucket, not the fs cache',
          '_build_graph_oci_cached()' in graph_handler, graph_handler)

    check('kg_builder shares its parsing between fs and oci',
          '_build_graph_from_raw(raw' in KG_RAW
          and KG_RAW.count('def _build_graph_from_raw') == 1,
          '— one function both _build_graph_fs and _build_graph_oci feed '
          'into; a second hand-written wikilink/tag extractor for oci is '
          'exactly the kind of copy that silently drifts')
    def _func_body(name):
        start = KG_RAW.index('def %s(' % name)
        nxt = KG_RAW.index('\ndef ', start + 1)
        return KG_RAW[start:nxt]

    check('...and both builders actually call it',
          'return _build_graph_from_raw' in _func_body('_build_graph_fs')
          and 'return _build_graph_from_raw' in _func_body('_build_graph_oci'),
          'each builder must feed its own raw list into the one shared '
          'parser rather than reimplementing extraction')

    # ── 2. the mechanism, run for real: a fake bucket, no live server ────
    names = [
        'pre/vendor-summary.md',
        'pre/.hidden/secret.md',       # hidden — must be excluded
        'pre/deck.pptx',               # non-text — must be excluded
        'pre/other.md',
        'pre/linker.md',
    ]
    contents = {
        'pre/vendor-summary.md': b'the vendor summary mentions Acme Corp pricing',
        'pre/.hidden/secret.md': b'vendor secret nobody should ever search',
        'pre/other.md': b'nothing relevant here',
        'pre/linker.md': b'# Linker\nsee [[vendor-summary]] for details\n#research',
    }
    fake = FakeOciClient(names, contents)

    import serve
    # A decoy local vault, filled with content that would surface if either
    # door were still silently falling through to the fs branch. If a
    # search/graph result ever contains anything from THIS directory, the
    # dispatch fix did not take.
    decoy_dir = Path(tempfile.mkdtemp(prefix='oci-decoy-vault-'))
    (decoy_dir / 'DECOY-vendor.md').write_text(
        'DECOY vendor content — must never appear in an oci-backend result',
        encoding='utf-8')

    orig = dict(_vault_backend=serve._vault_backend, _vault_root=serve._vault_root,
                _oci_object_client=serve._oci_object_client,
                _oci_vault_namespace=serve._oci_vault_namespace,
                _oci_vault_bucket=serve._oci_vault_bucket,
                _oci_vault_prefix=serve._oci_vault_prefix)
    try:
        serve._vault_backend = 'oci'
        serve._vault_root = str(decoy_dir)
        serve._oci_object_client = lambda: fake
        serve._oci_vault_namespace = 'ns'
        serve._oci_vault_bucket = 'bucket'
        serve._oci_vault_prefix = 'pre'

        result = serve._oci_vault_search('vendor', 'vendor', 10)
        paths = [h['path'] for h in result['hits']]
        check('search found the bucket hit',
              'vendor-summary.md' in paths, result)
        check('...ranked above the unrelated note',
              paths and paths[0] == 'vendor-summary.md', paths)
        check('...excluded the hidden path', 'secret.md' not in str(result), result)
        check('...never touched the decoy local vault',
              not any('DECOY' in str(v) for v in result.values()), result)
        check('...prefix was stripped from the returned path',
              all(not p.startswith('pre/') for p in paths), paths)

        import kg_builder
        kg_builder.init(
            vault_root=lambda: serve._vault_root,
            state_dir=lambda: Path(tempfile.mkdtemp(prefix='oci-state-')),
            memory_dir=lambda: Path(tempfile.mkdtemp(prefix='oci-mem-')),
            obsidian_request=lambda *a, **k: (0, {}, b''),
            oci_client=lambda: fake, oci_namespace=lambda: 'ns',
            oci_bucket=lambda: 'bucket', oci_prefix=lambda: 'pre')

        graph = kg_builder._build_graph_oci()
        # 'markdownvault' covers notes AND artifacts since #278 taught this
        # arm what the Library holds; split them so the two claims below stay
        # about the notes the builder actually reads.
        note_ids = sorted(n['id'] for n in graph['nodes']
                          if n.get('source') == 'markdownvault'
                          and n.get('type') != 'artifact')
        node_ids = sorted(n['id'] for n in graph['nodes']
                           if n.get('source') == 'markdownvault')
        check('graph built vault nodes from the bucket',
              note_ids == ['linker.md', 'other.md', 'vendor-summary.md'],
              note_ids)
        check('...and the filed deck rides along as an artifact node',
              'deck.pptx' in node_ids
              and next(n for n in graph['nodes']
                       if n['id'] == 'deck.pptx')['type'] == 'artifact',
              node_ids)
        check('...resolved the wikilink into a real edge',
              ('linker.md', 'vendor-summary.md') in
              [(e['source'], e['target']) for e in graph['edges']],
              graph['edges'])
        check('...picked up the tag',
              any(n['id'] == 'linker.md' and 'research' in n['tags']
                  for n in graph['nodes']),
              [n for n in graph['nodes'] if n['id'] == 'linker.md'])
        check('...excluded the hidden note, and never fetched the deck',
              'secret.md' not in node_ids
              and 'deck.pptx' not in note_ids,
              node_ids)
        check('...never touched the decoy local vault',
              not any('DECOY' in n.get('title', '') for n in graph['nodes']),
              node_ids)

        cached = kg_builder._build_graph_oci_cached()
        check('the cached build matches the direct build', cached == graph,
              '— same fake bucket, same call, must agree')
        sig1 = kg_builder._oci_vault_graph_signature()
        # The signature is a cheap fingerprint over list_objects metadata
        # only (name/size/time_modified) — it never fetches content, so it
        # can only notice an edit that shows up in that metadata. Prove
        # that by changing size, the field a real edit would actually move.
        names_with_size = [_FakeObj('pre/vendor-summary.md', size=1),
                            _FakeObj('pre/other.md', size=99),
                            _FakeObj('pre/linker.md', size=1)]
        fake2 = FakeOciClient([o.name for o in names_with_size], contents)
        fake2.list_objects = lambda ns, b, prefix='', fields='', limit=1000: _FakeResp(
            _FakeData(objects=names_with_size))
        serve._oci_object_client = lambda: fake2
        kg_builder.init(
            vault_root=lambda: serve._vault_root,
            state_dir=lambda: Path(tempfile.mkdtemp(prefix='oci-state2-')),
            memory_dir=lambda: Path(tempfile.mkdtemp(prefix='oci-mem2-')),
            obsidian_request=lambda *a, **k: (0, {}, b''),
            oci_client=lambda: fake2, oci_namespace=lambda: 'ns',
            oci_bucket=lambda: 'bucket', oci_prefix=lambda: 'pre')
        sig3 = kg_builder._oci_vault_graph_signature()
        check('a size change in the bucket listing changes the signature '
              '(the cheap fingerprint the cache keys on)',
              sig1 != sig3, [sig1, sig3])
    finally:
        for k, v in orig.items():
            setattr(serve, k, v)
        import shutil
        shutil.rmtree(decoy_dir, ignore_errors=True)

    print()
    if FAILS:
        print('%d check(s) failed:' % len(FAILS))
        for f in FAILS:
            print('  - ' + f)
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
