#!/usr/bin/env python3
"""A bucket-backed office filed a deck and got a map that had never heard of it.

"Put the Library's artifacts on the graph" (0dc7e2e) taught _build_graph_fs
that the Library holds more than markdown: decks, PDFs, charts and
spreadsheets became stat-only 'artifact' nodes, [[deck.pptx]] resolved to
them, ![](chart.png) became an 'embeds' edge, and the cache signature
statted every file so filing one invalidated the map. Its commit message
ends "OCI/REST builders unchanged" — and nobody came back for OCI.

So an office whose Library lives in an Object Storage bucket kept the old
answer. _build_graph_oci's one-line filter

    if not rel or rel.endswith('/') or not rel.endswith('.md'):
        continue

threw every non-note object away before _build_graph_from_raw ever saw it,
and never passed the `artifacts=` argument that function has taken since.
The deck was in /vault/list, findable by name in /vault/search, openable
in one click — and absent from the map. [[q3-deck.pptx]] in a note
resolved to nothing, ![](chart.png) made no edge, and the analytics mix
read "0 artifacts" for a Library full of them. The same single-suffix test
also dropped `.markdown` notes outright, which the fs builder reads.

Worse, _oci_vault_graph_signature skipped non-.md objects too, so uploading
or deleting a deck did not move the fingerprint the cache keys on: even
once the builder learned about artifacts, the boss would keep being served
the cached map from before the upload until an unrelated note happened to
change.

Fix: _build_graph_oci sorts the listing into notes (fetched) and artifacts
(stat only, never get_object'd) and hands both to the shared
_build_graph_from_raw, and the signature folds every listed object.

Run: python3 scripts/test_the_bucket_office_map_holds_the_librarys_artifacts_too.py
"""
import datetime
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
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
    """`objects` is a list of _FakeObj with FULL object names (prefix
    included); `contents` maps those same full names to bytes. A
    get_object for a name that isn't in `contents` raises — which is how
    this test proves the artifact branch never fetches artifact bytes."""
    def __init__(self, objects, contents):
        self.objects = objects
        self.contents = contents
        self.fetched = []

    def list_objects(self, namespace, bucket, prefix='', fields='', limit=1000):
        return _FakeResp(_FakeData(objects=list(self.objects)))

    def get_object(self, namespace, bucket, key):
        self.fetched.append(key)
        return _FakeResp(_FakeData(content=self.contents[key]))


def _wire(fake):
    import kg_builder
    nowhere = Path(tempfile.mkdtemp(prefix='oci-artifacts-state-'))
    kg_builder.init(
        vault_root=lambda: '',
        state_dir=lambda: nowhere,
        memory_dir=lambda: nowhere,
        obsidian_request=lambda *a, **k: (0, {}, b''),
        oci_client=lambda: fake, oci_namespace=lambda: 'ns',
        oci_bucket=lambda: 'bucket', oci_prefix=lambda: 'pre')
    return kg_builder


def main():
    print("the bucket office's map holds the Library's artifacts too")

    objects = [
        _FakeObj('pre/Research/brief.md', size=200),
        _FakeObj('pre/Research/chart.png', size=4096),
        _FakeObj('pre/q3-deck.pptx', size=90000),
        _FakeObj('pre/notes.markdown', size=40),
        _FakeObj('pre/.trash/gone.pdf', size=10),   # hidden — stays off the map
    ]
    contents = {
        'pre/Research/brief.md': (
            b'![c](Research/chart.png)\n'
            b'the deck is [[q3-deck.pptx]] and the picture is [[chart]]\n'),
        'pre/notes.markdown': b'a .markdown note the fs builder reads\n',
    }
    fake = FakeOciClient(objects, contents)
    kg = _wire(fake)

    graph = kg._build_graph_oci()
    nodes = {n['id']: n for n in graph['nodes']}
    edges = {(e['source'], e['target'], e['type']) for e in graph['edges']}
    B = 'Research/brief.md'

    check('a filed deck and chart are artifact nodes on the bucket map',
          nodes.get('q3-deck.pptx', {}).get('type') == 'artifact'
          and nodes.get('Research/chart.png', {}).get('type') == 'artifact',
          sorted(nodes))
    check('a .markdown note is still read as a note, not an artifact',
          nodes.get('notes.markdown', {}).get('type') == 'note',
          sorted(nodes))
    check('a dotted folder stays off the map',
          not any(n.startswith('.trash') or n.endswith('gone.pdf') for n in nodes),
          sorted(nodes))
    check('[[q3-deck.pptx]] resolves by exact path',
          (B, 'q3-deck.pptx', 'links_to') in edges, sorted(edges))
    check('[[chart]] resolves to the artifact by stem',
          (B, 'Research/chart.png', 'links_to') in edges, sorted(edges))
    check('![](embed) is an embeds edge',
          (B, 'Research/chart.png', 'embeds') in edges, sorted(edges))
    check('artifact bytes are never fetched — stat only',
          sorted(fake.fetched) == ['pre/Research/brief.md', 'pre/notes.markdown'],
          fake.fetched)
    check('the artifact carries the listing size the boss sees elsewhere',
          nodes.get('q3-deck.pptx', {}).get('size') == 90000,
          nodes.get('q3-deck.pptx'))
    check('inlinks count the arrivals at the chart',
          nodes.get('Research/chart.png', {}).get('inlinks') == 2,
          nodes.get('Research/chart.png'))

    # ── the cache fingerprint has to move when an artifact does ──────────
    sig1 = kg._oci_vault_graph_signature()
    fake2 = FakeOciClient(objects + [_FakeObj('pre/new-deck.pptx', size=1234)],
                          contents)
    kg2 = _wire(fake2)
    check('filing an artifact changes the cache signature',
          kg2._oci_vault_graph_signature() != sig1,
          '— a stale signature serves a map missing the newest filing')

    fake3 = FakeOciClient(
        [o for o in objects if o.name != 'pre/q3-deck.pptx'], contents)
    kg3 = _wire(fake3)
    check('deleting an artifact changes the cache signature',
          kg3._oci_vault_graph_signature() != sig1,
          '— otherwise the map keeps drawing a deck that is gone')

    print()
    if FAILS:
        print('%d check(s) failed:' % len(FAILS))
        for f in FAILS:
            print('  - ' + f)
        return 1
    print('all checks passed')
    return 0


sys.exit(main())
