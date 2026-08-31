"""Knowledge-graph builder — extracted from serve.py.

Builds the vault concept graph three ways (fs walk, Obsidian REST, HQ-state)
and caches the fs build behind a content signature. Pure logic: everything
environment-shaped (the vault root, state dirs, the Obsidian REST client)
comes in through init(), as callables where serve.py mutates the value at
runtime (the vault root is settable from the UI).
"""
import hashlib
import json
import sys
import os
import pathlib
import threading
import time
import urllib.parse

_cfg = {}


def init(*, vault_root, state_dir, memory_dir, obsidian_request,
         oci_client=None, oci_namespace=lambda: '', oci_bucket=lambda: '',
         oci_prefix=lambda: ''):
    """Called once by serve.py after its config globals exist. vault_root/
    state_dir/memory_dir/oci_namespace/oci_bucket/oci_prefix are ZERO-ARG
    CALLABLES (read fresh on every build — the OCI bucket, like the vault
    root, is settable from the UI); obsidian_request is serve's REST client
    function; oci_client is serve's _oci_object_client (itself already a
    zero-arg callable returning the lazily-built SDK client, same shape)."""
    _cfg.update(vault_root=vault_root, state_dir=state_dir,
                memory_dir=memory_dir, obsidian_request=obsidian_request,
                oci_client=oci_client, oci_namespace=oci_namespace,
                oci_bucket=oci_bucket, oci_prefix=oci_prefix)


import re as _re
_WIKILINK_RE = _re.compile(r'\[\[([^\]\|]+?)(?:\|[^\]]*)?\]\]')
_TAG_RE = _re.compile(r'(?:^|\s)#([A-Za-z0-9_/\-]+)')
# Three src spellings — <angle-bracketed>, %-encoded, plain — mirroring
# the preview renderer and the rename rewriter. Change together.
_EMBED_RE = _re.compile(r'!\[[^\]]*\]\((?:<([^>]+)>|([^)\s]+))\)')


def _graph_node_type(path: str, tags=None) -> str:
    """Lightweight product-facing graph taxonomy. Keep this intentionally small.
    The UI can reason with these without requiring a canonical backend schema yet."""
    p = (path or '').replace('\\', '/').lower()
    tagset = {str(t).lstrip('#').lower() for t in (tags or [])}
    name = pathlib.PurePosixPath(p).stem
    if 'research/' in p or 'research' in tagset:
        return 'research'
    if 'project' in tagset or p.startswith('projects/') or p.startswith('05-projects/') or '/projects/' in p:
        return 'project'
    if 'task' in tagset or 'tasks/' in p or 'todo' in name:
        return 'task'
    if 'agent' in tagset or name.startswith('agent-'):
        return 'agent'
    if 'agents/' in p:
        # `Agents/<name>/…` is a coworker's PRIVATE NOTES folder, not a note
        # ABOUT a coworker. Typing the whole subtree 'agent' meant every note
        # a coworker ever wrote became a person: the vault's own analysis
        # panel read "4 coworkers" for an office with two, the extras being
        # `Agents/Llama/notes/olives.md` and the boss. It scales with use —
        # ten private notes, ten phantom colleagues — and it is the panel a
        # boss reads to understand their own business.
        #
        # A file sitting DIRECTLY in agents/ is still a profile note about
        # someone; anything deeper belongs to that someone.
        parts = [x for x in p.split('/') if x]
        if 'agents' in parts and len(parts) - parts.index('agents') == 2:
            return 'agent'
        return 'memory'
    if 'decision' in tagset or 'decisions/' in p or 'decision' in name:
        return 'decision'
    if 'proposal' in tagset or 'proposal' in name or '/proposals/' in p:
        return 'proposal'
    if 'memory' in tagset or 'memory/' in p or 'memories/' in p:
        return 'memory'
    if 'risk' in tagset or 'risk' in name:
        return 'risk'
    if p.endswith(('.py.md', '.jsx.md', '.js.md', '.ts.md', '.tsx.md')) or 'code' in tagset:
        return 'code_file'
    return 'note'


def _graph_edge_payload(source: str, target: str, edge_type='links_to', status='canonical', confidence=1.0, source_text='') -> dict:
    return {
        'source': source,
        'target': target,
        'type': edge_type,
        'status': status,
        'confidence': confidence,
        'sourcePath': source,
        'sourceText': source_text,
    }


# ──────────────────────────────────────────────────────────────────────────
# Edge-type extraction (knowledge-graph style relationships)
#
# Every wikilink in a markdown file becomes an edge. By default that edge is
# `links_to` (the historical behavior). But we look at the SURROUNDING context
# of each link — section heading, callout type, line prefix, frontmatter key —
# to upgrade generic links into typed knowledge-graph relationships
# (cites, supports, contradicts, child_of, decided, blocked_by, etc).
#
# This makes the graph reason-able instead of just browse-able. Confidence
# stays high (>=0.7) for explicit cues; pure body links remain confidence 1.0
# typed links_to so we don't degrade the existing graph.
# ──────────────────────────────────────────────────────────────────────────

# Section heading → edge type for any links found INSIDE that section.
# Match is case-insensitive on the heading text; trailing punctuation stripped.
_SECTION_EDGE_TYPES = {
    'sources': 'cites',
    'source': 'cites',
    'references': 'cites',
    'reference': 'cites',
    'citations': 'cites',
    'see also': 'related_to',
    'related': 'related_to',
    'related notes': 'related_to',
    'further reading': 'related_to',
    'children': 'parent_of',
    'sub-pages': 'parent_of',
    'parent': 'child_of',
    'parents': 'child_of',
    'implementation': 'implements',
    'implemented by': 'implemented_by',
    'implements': 'implements',
    'risks': 'has_risk',
    'risk': 'has_risk',
    'decisions': 'decided',
    'decided': 'decided',
    'decision': 'decided',
    'evidence': 'supports',
    'supports': 'supports',
    'contradicts': 'contradicts',
    'objections': 'contradicts',
    'counter-evidence': 'contradicts',
    'blocks': 'blocks',
    'blocked by': 'blocked_by',
    'depends on': 'depends_on',
    'dependencies': 'depends_on',
    'supersedes': 'supersedes',
    'superseded by': 'superseded_by',
    'agents': 'created_by',
    'assigned to': 'assigned_to',
    'tasks': 'has_task',
    'proposals': 'has_proposal',
}

# A line that BEGINS with one of these prefixes (case-insensitive) and contains
# a wikilink is treated as a typed edge to that link. e.g. `Parent: [[Foo]]`.
_LINE_PREFIX_EDGE_TYPES = {
    'source': 'cites',
    'sources': 'cites',
    'cite': 'cites',
    'cites': 'cites',
    'reference': 'cites',
    'references': 'cites',
    'parent': 'child_of',
    'parents': 'child_of',
    'child': 'parent_of',
    'children': 'parent_of',
    'see also': 'related_to',
    'related': 'related_to',
    'implements': 'implements',
    'implemented by': 'implemented_by',
    'blocks': 'blocks',
    'blocked by': 'blocked_by',
    'depends on': 'depends_on',
    'depends': 'depends_on',
    'supersedes': 'supersedes',
    'superseded by': 'superseded_by',
    'replaces': 'supersedes',
    'replaced by': 'superseded_by',
    'assigned to': 'assigned_to',
    'assigned': 'assigned_to',
    'owner': 'assigned_to',
    'created by': 'created_by',
    'author': 'created_by',
    'authors': 'created_by',
    'edited by': 'edited_by',
    'reviewer': 'reviewed_by',
    'reviewed by': 'reviewed_by',
    'decision': 'decided',
    'decided': 'decided',
    'decides': 'decided',
    'note': 'notes',
    'tldr': 'notes',
    'summary': 'notes',
    'mention': 'mentions',
    'mentions': 'mentions',
}

# Callout block types (> [!type]) → edge type for links inside the callout.
_CALLOUT_EDGE_TYPES = {
    'supports': 'supports',
    'support': 'supports',
    'evidence': 'supports',
    'contradicts': 'contradicts',
    'contradict': 'contradicts',
    'refutes': 'contradicts',
    'objection': 'contradicts',
    'derived': 'derived_from',
    'derived-from': 'derived_from',
    'derives': 'derived_from',
    'cite': 'cites',
    'cites': 'cites',
    'source': 'cites',
    'note': 'notes',
    'info': 'notes',
    'abstract': 'notes',
    'summary': 'notes',
    'warning': 'has_risk',
    'caution': 'has_risk',
    'danger': 'has_risk',
    'risk': 'has_risk',
    'tip': 'related_to',
    'hint': 'related_to',
    'example': 'exemplifies',
    'decision': 'decided',
    'decided': 'decided',
    'todo': 'has_task',
    'task': 'has_task',
    'question': 'questions',
    'q': 'questions',
}

# Frontmatter key → (edge_type, is_inverse). is_inverse means the edge points
# FROM the linked target back TO this note (e.g. `children: [[X]]` means
# this note is parent_of X, but `parent: [[X]]` means this note is child_of X).
_FRONTMATTER_EDGE_TYPES = {
    'parent': ('child_of', False),
    'parents': ('child_of', False),
    'children': ('parent_of', False),
    'child': ('parent_of', False),
    'source': ('cites', False),
    'sources': ('cites', False),
    'cites': ('cites', False),
    'references': ('cites', False),
    'related': ('related_to', False),
    'see-also': ('related_to', False),
    'see_also': ('related_to', False),
    'supersedes': ('supersedes', False),
    'superseded-by': ('superseded_by', False),
    'replaces': ('supersedes', False),
    'replaced-by': ('superseded_by', False),
    'implements': ('implements', False),
    'implemented-by': ('implemented_by', False),
    'blocks': ('blocks', False),
    'blocked-by': ('blocked_by', False),
    'depends-on': ('depends_on', False),
    'depends': ('depends_on', False),
    'agent': ('created_by', False),
    'author': ('created_by', False),
    'authors': ('created_by', False),
    'created-by': ('created_by', False),
    'assigned-to': ('assigned_to', False),
    'assignedto': ('assigned_to', False),
    'assignee': ('assigned_to', False),
    'owner': ('assigned_to', False),
    'reviewer': ('reviewed_by', False),
    'reviewed-by': ('reviewed_by', False),
}

# Default confidence per type. Explicit frontmatter / line-prefix is 1.0;
# section context is 0.85 (fairly likely); callouts are 0.95 (explicit author
# intent). Generic body links_to stays at 1.0 (the link itself is a fact).
_EDGE_TYPE_CONFIDENCE = {
    'links_to': 1.0,
    'cites': 0.95,
    'related_to': 0.85,
    'child_of': 1.0,
    'parent_of': 1.0,
    'implements': 0.95,
    'implemented_by': 0.95,
    'blocks': 0.95,
    'blocked_by': 0.95,
    'supersedes': 1.0,
    'superseded_by': 1.0,
    'depends_on': 0.95,
    'supports': 0.95,
    'contradicts': 0.95,
    'derived_from': 0.95,
    'has_risk': 0.9,
    'decided': 0.9,
    'created_by': 1.0,
    'assigned_to': 1.0,
    'edited_by': 1.0,
    'reviewed_by': 1.0,
    'notes': 0.7,
    'mentions': 0.85,
    'has_task': 0.9,
    'has_proposal': 0.9,
    'exemplifies': 0.85,
    'questions': 0.85,
    # HQ-state ingestion edge types (tasks/missions/receipts/etc → vault)
    'references': 0.9,   # task/mission body mentions a note
    'produces':   0.95,  # mission wrote a note
    'modified':   0.85,  # receipt records a write to a note
    'targets':    0.85,  # mission scoped to a folder/note
    'runs_as':    1.0,   # mission runs as an agent
    # Message-registry edges
    'sent_to':    1.0,   # agent originated a message-thread
    'received':   1.0,   # agent received a message-thread
    # Org-chart edges
    'reports_to': 1.0,   # assistant agent → senior agent
}


_FRONTMATTER_RE = _re.compile(r'\A---\s*\n(.*?\n)---\s*\n', _re.DOTALL)
_HEADING_RE = _re.compile(r'^(#{1,6})\s+(.+?)\s*$')
_CALLOUT_OPEN_RE = _re.compile(r'^\s*>\s*\[!([A-Za-z][\w\-]*)\]')
# Grabs any line of the form "Word(s):" at the very start, captures the label.
_LINE_PREFIX_RE = _re.compile(r'^\s*(?:[-*]\s+)?\*{0,2}([A-Za-z][\w\s\-]{0,30}?)\*{0,2}\s*:\s*(.*)$')


def _norm_label(s: str) -> str:
    """Lowercase + collapse whitespace + strip trailing punctuation. Used to
    match section headings / line prefixes against the type lookup tables."""
    s = (s or '').strip().lower().rstrip('.:!?')
    return _re.sub(r'\s+', ' ', s)


def _classify_edge(context: dict) -> tuple:
    """Given the context surrounding a wikilink, return (edge_type, confidence,
    source_text). Priority: callout > line prefix > section heading > default.
    `context` keys: callout, prefix, section, line_text."""
    callout = context.get('callout')
    prefix  = context.get('prefix')
    section = context.get('section')
    text    = (context.get('line_text') or '').strip()[:240]
    if callout:
        t = _CALLOUT_EDGE_TYPES.get(callout.lower())
        if t:
            return t, _EDGE_TYPE_CONFIDENCE.get(t, 0.9), text
    if prefix:
        t = _LINE_PREFIX_EDGE_TYPES.get(_norm_label(prefix))
        if t:
            return t, _EDGE_TYPE_CONFIDENCE.get(t, 1.0), text
    if section:
        t = _SECTION_EDGE_TYPES.get(_norm_label(section))
        if t:
            return t, _EDGE_TYPE_CONFIDENCE.get(t, 0.85), text
    return 'links_to', 1.0, text


def _extract_typed_edges(rel: str, text: str, all_paths: dict):
    """Walk `text` line-by-line and yield (target_path, edge_type, confidence,
    source_text) for every resolvable wikilink, classifying each by its
    surrounding context. Also processes YAML frontmatter for typed metadata.

    Yields tuples; the caller dedups by (rel, target, type). We dedup on type
    too so a note can have BOTH a `cites` AND a `related_to` edge to the same
    target if the note links to it from two different contexts — useful for
    showing the strongest relationship while keeping evidence."""
    # ── Frontmatter pass ───────────────────────────────────────────────
    body = text
    fm_match = _FRONTMATTER_RE.match(text)
    if fm_match:
        fm_text = fm_match.group(1)
        body = text[fm_match.end():]
        for fm_line in fm_text.splitlines():
            kv = fm_line.split(':', 1)
            if len(kv) != 2: continue
            key = _norm_label(kv[0]).replace(' ', '-')
            val = kv[1].strip()
            mapping = _FRONTMATTER_EDGE_TYPES.get(key)
            if not mapping: continue
            edge_type, _ = mapping
            conf = _EDGE_TYPE_CONFIDENCE.get(edge_type, 0.9)
            for m in _WIKILINK_RE.finditer(val):
                tgt = _norm_link(m.group(1), all_paths)
                if tgt and tgt != rel:
                    yield (tgt, edge_type, conf, f'{key}: {val}'[:240])

    # ── Body pass: line-by-line, tracking section + callout state ──────
    current_section = None
    callout_type = None
    callout_lines_left = 0  # how many continuation `>` lines still belong to the open callout
    for line in body.splitlines():
        # Heading? Update current_section, no links here.
        h = _HEADING_RE.match(line)
        if h:
            current_section = h.group(2).strip()
            callout_type = None
            callout_lines_left = 0
            continue
        # Callout open?
        co = _CALLOUT_OPEN_RE.match(line)
        if co:
            callout_type = co.group(1)
            callout_lines_left = 12  # generous: callouts up to ~12 lines
        elif callout_type:
            # Callout continues only while line begins with `>`
            if line.lstrip().startswith('>') and callout_lines_left > 0:
                callout_lines_left -= 1
            else:
                callout_type = None
                callout_lines_left = 0
        # Line prefix?  (Only outside callouts; callouts already imply type.)
        prefix = None
        if not callout_type:
            lp = _LINE_PREFIX_RE.match(line)
            if lp:
                cand = lp.group(1)
                if _norm_label(cand) in _LINE_PREFIX_EDGE_TYPES:
                    prefix = cand
        # Now scan wikilinks on this line.
        for m in _WIKILINK_RE.finditer(line):
            tgt = _norm_link(m.group(1), all_paths)
            if not tgt or tgt == rel:
                continue
            # Obsidian's ![[file]] is an EMBED, not a mention — same edge
            # type the ![](src) parser below yields, so the graph doesn't
            # split one relationship across two names.
            if m.start() > 0 and line[m.start() - 1] == '!':
                yield (tgt, 'embeds', 0.95, line.strip())
                continue
            ctx = {
                'callout': callout_type,
                'prefix': prefix,
                'section': current_section,
                'line_text': line.strip(),
            }
            etype, conf, text_snip = _classify_edge(ctx)
            yield (tgt, etype, conf, text_snip)

def _norm_link(target: str, all_paths: dict) -> str:
    """Resolve a wikilink target string to a known path key, or '' if unknown.
    Wikilinks can be by stem ("Foo") or path ("dir/Foo"); the .md is implicit."""
    target = target.strip()
    if not target:
        return ''
    # Strip section anchors (#heading) and block refs (^id)
    for sep in ('#', '^'):
        i = target.find(sep)
        if i >= 0: target = target[:i]
    if not target:
        return ''
    candidates = [
        target,
        target + '.md',
        target.rstrip('/') + '.md',
    ]
    # Lowercase fallback for case-insensitive matching
    by_stem = all_paths['by_stem']
    by_path = all_paths['by_path']
    for c in candidates:
        if c in by_path:
            return c
    stem = pathlib.PurePosixPath(target).stem.lower()
    return by_stem.get(stem, '')


def _build_graph_from_raw(raw, artifacts=()) -> dict:
    """Shared second half of every backend's graph build. `raw` is a list of
    (rel, title, text, mtime_seconds, size) tuples — that's the ENTIRE
    contract a backend has to satisfy, whether the text came from a local
    file read, an Obsidian REST fetch, or an OCI get_object. Wikilink/tag/
    typed-edge extraction and the HQ-state overlay live here exactly once,
    so a bug fixed for one backend is fixed for all of them and a fourth
    backend added later inherits this for free instead of needing its own
    copy that can drift from this one.

    `artifacts` is a list of (rel, title, mtime_seconds, size) for the
    Library's NON-markdown residents — decks, PDFs, images, spreadsheets.
    They become 'artifact' nodes, [[wikilinks]] resolve to them (notes win
    a shared stem), and a note's ![](embed) becomes an 'embeds' edge."""
    by_path = {}
    by_stem = {}
    for rel, title, _text, _mtime, _size in raw:
        by_path[rel] = True
        by_stem[title.lower()] = rel
    for rel, title, _mtime, _size in artifacts:
        by_path[rel] = True
        by_stem.setdefault(title.lower(), rel)
    all_paths = {'by_path': by_path, 'by_stem': by_stem}
    nodes = []
    edges = []
    # Dedupe by (source, target, type) so a note can have multiple edge types
    # to the same target (e.g. cited AND related_to) but never duplicates
    # within a single type. We also track per-pair best-confidence to upgrade
    # repeat plain links_to into typed edges if a typed mention shows up later.
    seen_typed_edge = set()
    for rel, title, text, mtime, size in raw:
        tags = sorted(set(m.group(1) for m in _TAG_RE.finditer(text)))
        out_targets = set()
        # Walk every (target, type, conf, snippet) the extractor finds.
        for tgt, etype, conf, snip in _extract_typed_edges(rel, text, all_paths):
            out_targets.add(tgt)
            key = (rel, tgt, etype)
            if key in seen_typed_edge: continue
            seen_typed_edge.add(key)
            edges.append(_graph_edge_payload(
                rel, tgt, edge_type=etype, confidence=conf, source_text=snip))
        # ![](embed) — the note SHOWS the artifact, which is a stronger tie
        # than mentioning it. External/data/rooted srcs aren't Library
        # residents and stay out (mirrors the preview's routing test).
        for m in _EMBED_RE.finditer(text):
            src = urllib.parse.unquote(m.group(1) or m.group(2))
            if _re.match(r'^(https?:|data:|/)', src, _re.IGNORECASE):
                continue
            tgt = src if src in by_path else by_stem.get(
                pathlib.PurePosixPath(src).stem.lower(), '')
            if not tgt or tgt == rel:
                continue
            out_targets.add(tgt)
            key = (rel, tgt, 'embeds')
            if key in seen_typed_edge: continue
            seen_typed_edge.add(key)
            edges.append(_graph_edge_payload(
                rel, tgt, edge_type='embeds', source_text=m.group(0)[:120]))
        nodes.append({
            'id': rel, 'title': title, 'path': rel,
            'mtime': int(mtime * 1000), 'size': size,
            'tags': tags[:8], 'outlinks': len(out_targets),
            'type': _graph_node_type(rel, tags),
            'source': 'markdownvault',
        })

    for rel, title, mtime, size in artifacts:
        nodes.append({
            'id': rel, 'title': title, 'path': rel,
            'mtime': int(mtime * 1000), 'size': size,
            'tags': [], 'outlinks': 0,
            'type': 'artifact',
            'source': 'markdownvault',
        })

    # ── HQ-state ingestion: tasks/projects/missions/receipts/agents ────
    # The graph stops being a vault-only viewer and starts representing
    # everything CafresoHQ knows. New nodes use prefixed IDs (`task:`,
    # `agent:` etc) so they never collide with vault paths. Edges link
    # them to each other AND to vault notes when references resolve.
    hq_nodes, hq_edges = _build_hq_state_graph(all_paths, seen_typed_edge)
    nodes.extend(hq_nodes)
    edges.extend(hq_edges)

    # Compute inlinks for sizing — across BOTH vault and HQ-state nodes.
    indeg = {n['id']: 0 for n in nodes}
    for e in edges:
        if e['target'] in indeg:
            indeg[e['target']] += 1
    for n in nodes:
        n['inlinks'] = indeg[n['id']]
    return {'nodes': nodes, 'edges': edges}


def _build_graph_fs() -> dict:
    """Build a graph from the files under the configured vault directory:
    .md notes are read and parsed; everything else the Library holds —
    decks, PDFs, images, spreadsheets — rides along as artifact nodes
    (stat only, never read)."""
    if not _cfg['vault_root']():
        raise ValueError('vault not configured')
    root = pathlib.Path(_cfg['vault_root']()).resolve()
    raw = []
    artifacts = []
    for p in root.rglob('*'):
        if not p.is_file():
            continue
        try:
            rel = str(p.relative_to(root)).replace('\\', '/')
        except ValueError:
            continue
        if any(part.startswith('.') for part in p.relative_to(root).parts):
            continue
        try:
            st = p.stat()
        except OSError:
            continue
        if p.suffix.lower() in ('.md', '.markdown'):
            try:
                text = p.read_text(encoding='utf-8', errors='replace')
            except OSError:
                continue
            raw.append((rel, p.stem, text, st.st_mtime, st.st_size))
        else:
            artifacts.append((rel, p.stem, st.st_mtime, st.st_size))
    return _build_graph_from_raw(raw, artifacts=artifacts)


def _oci_graph_prefix() -> str:
    raw = _cfg['oci_prefix']()
    return (raw.rstrip('/') + '/') if raw else ''


def _build_graph_oci() -> dict:
    """The OCI-backend twin of _build_graph_fs — list the bucket's markdown
    objects, fetch each one's content, and hand the same (rel, title, text,
    mtime, size) shape to _build_graph_from_raw. Measured need: /vault/graph
    dispatched on `_vault_backend == 'rest'` else fs, which meant an OCI
    office — /vault/list, /vault/file and DELETE all correctly branch three
    ways — got the FS builder pointed at whatever _vault_root happens to be
    (usually unrelated to the bucket, often nothing), silently returning an
    empty or wrong graph instead of the bucket's actual notes."""
    if not (_cfg['oci_namespace']() and _cfg['oci_bucket']()):
        raise ValueError('OCI vault not configured')
    cli = _cfg['oci_client']()
    prefix = _oci_graph_prefix()
    resp = cli.list_objects(
        _cfg['oci_namespace'](), _cfg['oci_bucket'](),
        prefix=prefix, fields='name,size,timeModified', limit=1000)
    raw = []
    for obj in resp.data.objects:
        rel = obj.name[len(prefix):] if prefix else obj.name
        if not rel or rel.endswith('/') or not rel.endswith('.md'):
            continue
        if any(part.startswith('.') for part in rel.split('/')):
            continue
        try:
            content = cli.get_object(
                _cfg['oci_namespace'](), _cfg['oci_bucket'](), obj.name).data.content
        except Exception:
            continue  # listed but unreadable (e.g. raced a delete) — skip it, don't fail the whole graph
        text = content.decode('utf-8', 'replace')
        mtime = obj.time_modified.timestamp() if obj.time_modified else 0
        raw.append((rel, pathlib.PurePosixPath(rel).stem, text, mtime, obj.size or 0))
    return _build_graph_from_raw(raw)


# ──────────────────────────────────────────────────────────────────────────
# Graph build cache (FS backend)
#
# /vault/graph rebuilds by reading + parsing every .md file and the hq-state
# JSON on each call — O(total text). On a cold container or a big vault that's
# a slow first paint of the graph. This cache keys the built graph on a CHEAP
# stat-only signature (each file's mtime+size, no reads); a repeat call with no
# file changes returns the cached graph instantly. Any edit/add/delete changes
# the signature and triggers exactly one rebuild. Single-process, so a plain
# module global under the server's thread is sufficient.
# ──────────────────────────────────────────────────────────────────────────

_graph_cache = {'sig': None, 'graph': None}
_graph_cache_lock = threading.Lock()
_oci_graph_cache = {'sig': None, 'graph': None}
_oci_graph_cache_lock = threading.Lock()


def _hq_state_sig_update(h) -> None:
    """Fold the hq-state JSON files' (name, mtime, size) into a running
    hash. The state dir is backend-agnostic — it's not where vault content
    lives, it's tasks/projects/missions/agents — so every backend's cache
    signature needs this same contribution. Factored out so 'oci' didn't
    grow its own hand-copied loop next to fs's, which is exactly the kind
    of copy that drifts (see the OCI-delete ticket two entries up)."""
    try:
        for jp in sorted(_cfg['state_dir']().glob('*.json')):
            try:
                st = jp.stat()
                h.update(('S:%s|%d|%d\n' % (jp.name, int(st.st_mtime), st.st_size)).encode('utf-8'))
            except OSError:
                pass
    except OSError:
        pass


def _vault_graph_signature() -> str:
    """Cheap fingerprint of everything _build_graph_fs reads: each vault
    file's (rel, mtime, size) — notes AND artifacts, since both are nodes
    now — + the top-level hq-state JSON files. Stat-only, so it's far
    cheaper than the read+parse a full rebuild does."""
    if not _cfg['vault_root']():
        return 'unconfigured'
    h = hashlib.sha1()
    root = pathlib.Path(_cfg['vault_root']()).resolve()
    try:
        for p in sorted(x for x in root.rglob('*') if x.is_file()):
            try:
                rel = p.relative_to(root)
            except ValueError:
                continue
            if any(part.startswith('.') for part in rel.parts):
                continue
            try:
                st = p.stat()
            except OSError:
                continue
            h.update(('%s|%d|%d\n' % (str(rel).replace('\\', '/'), int(st.st_mtime), st.st_size)).encode('utf-8'))
    except OSError:
        return 'walk-error'
    _hq_state_sig_update(h)
    return h.hexdigest()


def _build_graph_fs_cached() -> dict:
    """_build_graph_fs() with an mtime-signature cache (see above)."""
    sig = _vault_graph_signature()
    with _graph_cache_lock:
        if _graph_cache['sig'] == sig and _graph_cache['graph'] is not None:
            return _graph_cache['graph']
    graph = _build_graph_fs()
    with _graph_cache_lock:
        _graph_cache['sig'] = sig
        _graph_cache['graph'] = graph
    return graph


def _oci_vault_graph_signature() -> str:
    """Cheap fingerprint of everything _build_graph_oci reads: ONE
    list_objects call's (name, size, timeModified) per markdown object — no
    content fetched, same 'stat, don't read' shape as the fs signature —
    plus the same hq-state contribution every backend's cache uses."""
    if not (_cfg['oci_namespace']() and _cfg['oci_bucket']()):
        return 'unconfigured'
    h = hashlib.sha1()
    try:
        cli = _cfg['oci_client']()
        prefix = _oci_graph_prefix()
        resp = cli.list_objects(
            _cfg['oci_namespace'](), _cfg['oci_bucket'](),
            prefix=prefix, fields='name,size,timeModified', limit=1000)
        for obj in sorted(resp.data.objects, key=lambda o: o.name):
            if not obj.name.endswith('.md'):
                continue
            tm = obj.time_modified.timestamp() if obj.time_modified else 0
            h.update(('%s|%d|%d\n' % (obj.name, int(tm), obj.size or 0)).encode('utf-8'))
    except Exception:
        return 'list-error'
    _hq_state_sig_update(h)
    return h.hexdigest()


def _build_graph_oci_cached() -> dict:
    """_build_graph_oci() with a signature cache — see _build_graph_fs_cached.
    A repeat call with no bucket changes and no hq-state changes returns
    instantly instead of re-fetching every markdown object's content."""
    sig = _oci_vault_graph_signature()
    with _oci_graph_cache_lock:
        if _oci_graph_cache['sig'] == sig and _oci_graph_cache['graph'] is not None:
            return _oci_graph_cache['graph']
    graph = _build_graph_oci()
    with _oci_graph_cache_lock:
        _oci_graph_cache['sig'] = sig
        _oci_graph_cache['graph'] = graph
    return graph


# ──────────────────────────────────────────────────────────────────────────
# HQ-state → graph ingestion
#
# Reads the JSON files in hq-state/ and turns them into typed graph nodes,
# with edges to each other AND to vault notes when references resolve. This
# is what makes GraphView the unified "everything CafresoHQ knows" view
# rather than just a markdown vault visualizer.
# ──────────────────────────────────────────────────────────────────────────

def _hq_state_path(name: str) -> pathlib.Path:
    """Resolve `hq-state/<name>.json` relative to the configured state dir."""
    return _cfg['state_dir']() / f'{name}.json'


def _load_hq_state(name: str):
    """Safely load `hq-state/<name>.json`. Returns [] / {} on missing/invalid;
    never raises so a missing file doesn't break the whole graph build."""
    p = _hq_state_path(name)
    if not p.exists():
        return None
    try:
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        sys.stderr.write(f'[graph] could not load {name}.json: {e}\n')
        return None


def _load_hq_memory(name: str):
    """Safely load `<hq-memory>/<name>.json`. Same shape contract as
    _load_hq_state but reads from _cfg['memory_dir']() (where the CafresoHQ
    frontend persists agents, journals, etc via useFileStored('memory', ...))."""
    p = _cfg['memory_dir']() / f'{name}.json'
    if not p.exists():
        return None
    try:
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        sys.stderr.write(f'[graph] could not load memory/{name}.json: {e}\n')
        return None


def _load_authoritative_agents() -> dict:
    """Load the canonical agents list from hq-memory/agents.json (where the
    CafresoHQ frontend persists hired agents). Returns a dict keyed by both
    the agent id (e.g. 'a_nykw53') AND its name (e.g. 'Selvin'), with the
    agent dict as value. This lets the graph builder upgrade synthesised
    agent nodes — which would otherwise show as 'a_nykw53' — to friendly
    names ('Selvin · Code Gremlin') with proper sprite color metadata."""
    raw = _load_hq_memory('agents') or []
    if not isinstance(raw, list):
        return {}
    by_key = {}
    for a in raw:
        if not isinstance(a, dict): continue
        aid = a.get('id') or ''
        name = a.get('name') or ''
        if aid:  by_key[aid.lower()] = a
        if name: by_key[name.lower()] = a
    return by_key


def _slug_agent(s: str) -> str:
    """Normalize an agent name/id into a stable graph node id suffix."""
    return _re.sub(r'[^A-Za-z0-9_]+', '_', (s or 'unknown').strip()).strip('_').lower() or 'unknown'


def _build_hq_state_graph(all_paths: dict, seen_typed_edge: set) -> tuple:
    """Return (nodes, edges) ingested from hq-state/. Safe to call even if
    no JSON files exist — returns ([], []) in that case.

    `all_paths` is the same {by_path, by_stem} the wikilink resolver uses;
    we reuse it so when a task.detail mentions [[NoteName]] we can build a
    proper edge to the actual vault note.

    `seen_typed_edge` is the dedup set from the vault pass; we extend it
    so HQ-state edges don't duplicate vault edges by accident."""
    nodes_out = []
    edges_out = []

    def add_edge(src, tgt, etype, conf, snippet=''):
        key = (src, tgt, etype)
        if key in seen_typed_edge: return
        seen_typed_edge.add(key)
        edges_out.append(_graph_edge_payload(
            src, tgt, edge_type=etype, confidence=conf, source_text=snippet))

    # Authoritative agent registry (hq-memory/agents.json). Lookup by either
    # id or name. When a task/mission/receipt references an agent, we use
    # this to get the friendly name + role + color so the graph node is
    # readable ('Selvin · Code Gremlin') instead of opaque ('a_nykw53').
    auth_agents = _load_authoritative_agents()

    def _resolve_agent_meta(agent_ref: str):
        """Return the canonical agent dict for a given id-or-name reference,
        or None if the registry doesn't know about it. Case-insensitive."""
        if not agent_ref: return None
        return auth_agents.get(str(agent_ref).lower())

    # Track agent identities we've seen — keyed by canonical slug. We unify
    # references so 'Selvin', 'a_nykw53', and 'selvin' all collapse to one
    # node. Slug derives from the canonical id when known, else from the
    # raw reference (so unknown agents still get a node, just unbranded).
    agents_by_slug = {}  # slug → {'id', 'title', 'role', 'color', 'sourceIds', 'roles', 'meta'}

    def note_agent(agent_id_or_name: str, role: str = '', display: str = ''):
        """Register an agent reference; returns the slug node id. If the
        registry knows this agent, all later refs (by id or by name) collapse
        to the same slug — which is critical because tasks reference agents
        by id (a_xxx) but receipts reference them by name (Selvin)."""
        if not agent_id_or_name:
            return None
        meta = _resolve_agent_meta(agent_id_or_name)
        # Canonical slug: from the agent's own id if registry knows them,
        # else from the literal reference. This is what unifies cross-refs.
        canonical = (meta.get('id') if meta else str(agent_id_or_name))
        slug = _slug_agent(canonical)
        rec = agents_by_slug.get(slug)
        if not rec:
            rec = {
                'id': f'agent:{slug}',
                # `display` matters for participants the registry does NOT know —
                # above all the boss, whose friendly name was computed as
                # "You (boss)" and then dropped, so the map showed a node
                # simply called "boss" among the coworkers. Registry members
                # are relabelled below from their own record, so this only
                # fills a gap rather than overriding anything.
                'title': str(display or agent_id_or_name),
                'role': '',
                'color': None,
                'meta': None,
                'sourceIds': set(),
                'roles': set(),
            }
            agents_by_slug[slug] = rec
        # Apply registry data when available — friendly name wins over a_xxx.
        if meta:
            rec['title'] = meta.get('name') or rec['title']
            rec['role']  = meta.get('role') or rec['role']
            rec['color'] = meta.get('color') or rec['color']
            rec['meta']  = meta
        else:
            # Fallback heuristic: prefer non-`a_xxx` displays when no registry hit.
            new = str(agent_id_or_name)
            if rec['title'].startswith('a_') and not new.startswith('a_'):
                rec['title'] = new
        rec['sourceIds'].add(str(agent_id_or_name))
        if role: rec['roles'].add(role)
        return rec['id']

    def resolve_wikilinks_in(text: str):
        """Yield resolved vault paths for every wikilink in `text`."""
        if not text: return
        for m in _WIKILINK_RE.finditer(text):
            tgt = _norm_link(m.group(1), all_paths)
            if tgt: yield tgt

    def resolve_path_to_note(p: str) -> str:
        """If `p` looks like a path that ends in a markdown filename we know,
        return the resolved vault path. Used to wire receipts whose title is
        e.g. 'FILE_WRITE: graphview_design_doc.md' to the actual note."""
        if not p: return ''
        # Try the literal stem.
        stem = pathlib.PurePosixPath(p.replace('\\', '/')).stem
        return all_paths['by_stem'].get(stem.lower(), '')

    # ── Tasks ──────────────────────────────────────────────────────────
    tasks = _load_hq_state('tasks') or []
    if isinstance(tasks, list):
        for t in tasks:
            if not isinstance(t, dict): continue
            tid = t.get('id') or ''
            if not tid: continue
            node_id = f'task:{tid}'
            title = (t.get('title') or '(untitled task)')[:120]
            detail = t.get('detail') or ''
            status = t.get('status') or ''
            priority = t.get('priority') or ''
            assigned = t.get('assignedTo')
            created = t.get('createdAt') or 0
            tags = [f'status/{status}'] if status else []
            if priority: tags.append(f'priority/{priority}')
            nodes_out.append({
                'id': node_id, 'title': title, 'path': '',
                'mtime': int(created) if created else 0,
                'size': len(detail) + len(title),
                'tags': tags, 'outlinks': 0,
                'type': 'task',
                'source': 'hq-state',
            })
            # Edges
            if assigned:
                aid = note_agent(assigned, 'assignee')
                if aid: add_edge(node_id, aid, 'assigned_to', 1.0,
                                  f'task assigned to {assigned}')
            for ref in resolve_wikilinks_in(title + '\n' + detail):
                add_edge(node_id, ref, 'references', 0.9,
                          f'task body mentions [[{pathlib.PurePosixPath(ref).stem}]]')
            # The filed deliverable. When a coworker's answer lands in the
            # Library the task record keeps the exact vault path it filed
            # (artifactPath) — and this builder ignored it, so a done task
            # and the very note it produced sat on the map as strangers.
            # Same `produces` type the missions' notesWritten edges wear:
            # the palette and both renderers already know it by name.
            artifact = str(t.get('artifactPath') or '').replace('\\', '/').strip().lstrip('/')
            if artifact and artifact not in all_paths['by_path']:
                artifact = resolve_path_to_note(artifact)   # moved/renamed since
            if artifact:
                add_edge(node_id, artifact, 'produces', 1.0,
                          f'task delivered {artifact}')

    # ── Projects ───────────────────────────────────────────────────────
    projects = _load_hq_state('projects') or []
    if isinstance(projects, list):
        for p in projects:
            if not isinstance(p, dict): continue
            pid = p.get('id') or ''
            if not pid: continue
            node_id = f'project:{pid}'
            name = p.get('name') or '(unnamed project)'
            ptype = p.get('type') or 'local'
            agentIds = p.get('agentIds') or []
            created = p.get('createdAt') or 0
            tags = [f'project-type/{ptype}']
            nodes_out.append({
                'id': node_id, 'title': name, 'path': p.get('path') or '',
                'mtime': int(created) if created else 0,
                'size': 0, 'tags': tags, 'outlinks': 0,
                'type': 'project',
                'source': 'hq-state',
            })
            for aid_raw in agentIds:
                aid = note_agent(aid_raw, 'project-member')
                if aid: add_edge(node_id, aid, 'assigned_to', 1.0,
                                  f'project includes agent {aid_raw}')

    # ── Missions ───────────────────────────────────────────────────────
    missions = _load_hq_state('missions') or []
    if isinstance(missions, list):
        for m in missions:
            if not isinstance(m, dict): continue
            mid = m.get('id') or ''
            if not mid: continue
            node_id = f'mission:{mid}'
            mtype = m.get('type') or 'mission'
            agent = m.get('agentId')
            topic = m.get('topic') or ''
            folder = m.get('vaultFolder') or ''
            started = m.get('startedAt') or 0
            status = m.get('status') or ''
            iters = m.get('iterations') or 0
            written = m.get('notesWritten') or []
            tags = [f'mission-type/{mtype}']
            if status: tags.append(f'status/{status}')
            short_topic = topic.split('.')[0][:80] if topic else ''
            title = f'{mtype.title()}: {short_topic}' if short_topic else f'{mtype.title()} mission'
            nodes_out.append({
                'id': node_id, 'title': title, 'path': '',
                'mtime': int(started) if started else 0,
                'size': len(topic), 'tags': tags, 'outlinks': 0,
                'type': 'mission',
                'source': 'hq-state',
            })
            if agent:
                aid = note_agent(agent, 'mission-runner')
                if aid: add_edge(node_id, aid, 'runs_as', 1.0,
                                  f'mission runs as {agent}')
            # Mission topic mentioning [[wikilinks]] → references
            for ref in resolve_wikilinks_in(topic):
                add_edge(node_id, ref, 'references', 0.9, 'mission topic')
            # `notesWritten` array → produces edges to those vault notes.
            if isinstance(written, list):
                for w in written[:50]:
                    rel = ''
                    if isinstance(w, str):
                        rel = w.replace('\\','/').lstrip('/')
                        if rel and rel not in all_paths['by_path']:
                            # Try stem fallback.
                            rel = resolve_path_to_note(rel)
                    elif isinstance(w, dict):
                        rel = (w.get('path') or '').replace('\\','/').lstrip('/')
                        if rel and rel not in all_paths['by_path']:
                            rel = resolve_path_to_note(rel)
                    if rel:
                        add_edge(node_id, rel, 'produces', 0.95,
                                  f'mission wrote {rel}')
            # If vaultFolder maps to a known folder root, edge to the index/MOC note in it.
            if folder:
                fp = folder.replace('\\','/').strip('/')
                # Look for an index-ish note inside that folder.
                for cand in (f'{fp}/index.md', f'{fp}/README.md', f'{fp}/{pathlib.PurePosixPath(fp).name}.md'):
                    if cand in all_paths['by_path']:
                        add_edge(node_id, cand, 'targets', 0.85, f'mission folder: {fp}')
                        break

    # ── Receipts ───────────────────────────────────────────────────────
    receipts = _load_hq_state('receipts') or []
    if isinstance(receipts, list):
        for r in receipts:
            if not isinstance(r, dict): continue
            rid = r.get('id') or ''
            if not rid: continue
            node_id = f'receipt:{rid}'
            title = (r.get('title') or '(untitled receipt)')[:120]
            kind = r.get('kind') or ''
            decision = r.get('decision') or ''
            decided_at = r.get('decidedAt') or 0
            elevated = r.get('elevated', False)
            by_agent = r.get('by') or ''
            tags = []
            if kind: tags.append(f'receipt-kind/{kind}')
            if decision: tags.append(f'decision/{decision}')
            if elevated: tags.append('elevated')
            # Use type 'decision' for explicit decisions, 'receipt' for tool-execution audit.
            ntype = 'decision' if decision in ('approved', 'rejected') else 'receipt'
            nodes_out.append({
                'id': node_id, 'title': title, 'path': '',
                'mtime': int(decided_at) if decided_at else 0,
                'size': 0, 'tags': tags, 'outlinks': 0,
                'type': ntype,
                'source': 'hq-state',
            })
            if by_agent:
                aid = note_agent(by_agent, 'receipt-actor')
                if aid:
                    etype = 'decided' if ntype == 'decision' else 'created_by'
                    add_edge(node_id, aid, etype, 1.0, f'receipt by {by_agent}')
            # If the receipt title looks like a file action, link to the affected note.
            # e.g. "FILE_WRITE: foo.md" or "EDIT: bar/baz.md".
            m = _re.search(r':\s*(\S+\.md)\b', title)
            if m:
                cand = resolve_path_to_note(m.group(1))
                if cand:
                    affect_type = {
                        'tool-execution': 'modified',
                    }.get(kind, 'references')
                    add_edge(node_id, cand, affect_type, 0.85, title)

    # Add every registry agent up front so even agents who haven't been
    # referenced by any task/mission/receipt still show up in the graph
    # (otherwise newly-hired agents are invisible until they do work).
    # We also seed `reports_to` edges here so the org-chart structure is
    # visible even for assistants who haven't done work yet.
    pending_reports_to = []  # [(assistant_aid_ref, senior_aid_ref)]
    for key, meta in auth_agents.items():
        # Skip duplicate entries — registry indexes by both id and name.
        aid = meta.get('id')
        if not aid: continue
        if key.lower() != aid.lower(): continue
        note_agent(aid)
        # If this agent has a senior (reportsTo set in agents.json), record
        # it for an edge — we resolve both ends to canonical agent slugs
        # AFTER all agents are noted (so the senior exists in the graph
        # regardless of registration order).
        senior_id = meta.get('reportsTo') or meta.get('parentAgentId')
        if senior_id:
            pending_reports_to.append((aid, senior_id, meta.get('name') or aid))
    # Resolve pending reports_to edges now that all agents are noted.
    for assistant_id, senior_id, assistant_name in pending_reports_to:
        a_node = note_agent(assistant_id, 'assistant')
        s_node = note_agent(senior_id, 'senior')
        if a_node and s_node and a_node != s_node:
            add_edge(a_node, s_node, 'reports_to', 1.0,
                     f'{assistant_name} reports to senior')

    # ── Messages: agent-comms registry (Phase 1 of comms refactor) ─────
    # The frontend's MessageRegistry persists every agent↔agent handoff to
    # hq-state/messages.json. Each thread becomes a `message-thread` node
    # in the graph with edges to the participating agents — so the boss can
    # see live conversations as visual structure, not just inbox rows.
    # Per-message nodes would explode the graph on busy days; per-thread
    # gives one node per coherent conversation which is far more readable.
    messages = _load_hq_state('messages') or []
    if isinstance(messages, list) and messages:
        # Group messages into threads (preserving creation order).
        threads = {}
        for m in messages:
            if not isinstance(m, dict): continue
            tid = m.get('threadId') or ''
            if not tid: continue
            threads.setdefault(tid, []).append(m)
        for tid, thread_msgs in threads.items():
            thread_msgs.sort(key=lambda m: m.get('createdAt') or 0)
            head = thread_msgs[0]
            tail = thread_msgs[-1]
            node_id = f'thread:{tid}'
            # Display: "Selvin ↔ Plato (3)" or "boss → Selvin"
            from_n = head.get('fromAgentName') or head.get('fromAgentId') or '?'
            to_n   = head.get('toAgentName')   or head.get('toAgentId')   or '?'
            count = len(thread_msgs)
            title = f'{from_n} → {to_n}'
            if count > 1: title += f' ({count})'
            # Body preview = first message body, truncated.
            body_preview = (head.get('body') or '').split('\n')[0][:90]
            # State: take the latest non-terminal state if any (so an
            # otherwise-completed thread with a new in-progress reply
            # surfaces as in_progress); else take the tail's terminal state.
            terminal_states = {'completed', 'failed', 'cancelled'}
            current_state = tail.get('state') or 'queued'
            for m in reversed(thread_msgs):
                if m.get('state') and m['state'] not in terminal_states:
                    current_state = m['state']; break
            tags = [f'state/{current_state}']
            # Promote priority/taskType to tags for filtering.
            if head.get('priority') and head['priority'] != 'med':
                tags.append(f'priority/{head["priority"]}')
            if head.get('taskType'):
                tags.append(f'task-type/{head["taskType"]}')
            # Aggregate failure cause across thread (any failed msg => tagged).
            had_failure = any(m.get('state') == 'failed' for m in thread_msgs)
            if had_failure: tags.append('had-failure')
            updated = max((m.get('updatedAt') or m.get('createdAt') or 0) for m in thread_msgs)
            nodes_out.append({
                'id': node_id,
                'title': title,
                'path': '',
                'mtime': int(updated) if updated else 0,
                'size': sum(len(m.get('body') or '') for m in thread_msgs),
                'tags': tags,
                'outlinks': 0,
                'type': 'message-thread',
                'source': 'hq-state',
                'messageCount': count,
                'threadState': current_state,
                'preview': body_preview,
            })
            # Edges: thread → each unique participant agent. Use 'sent_to'
            # for the from→thread direction and 'received' for to→thread,
            # so the graph reads as "agent originates / agent receives this
            # conversation". Boss participation collapses into a 'boss'
            # synthetic agent so it's visible in the graph too.
            participants = set()
            for m in thread_msgs:
                fid = m.get('fromAgentId') or ''
                tid_ag = m.get('toAgentId') or ''
                if fid and fid != 'boss': participants.add((fid, m.get('fromAgentName') or fid, 'sender'))
                elif fid == 'boss': participants.add(('boss', 'You (boss)', 'sender'))
                if tid_ag: participants.add((tid_ag, m.get('toAgentName') or tid_ag, 'receiver'))
            for ag_id, ag_name, role in participants:
                # ag_name was unpacked and discarded — the third dead value of
                # its kind found this session, after agent.tasksDone and the
                # userText parameter. Computing a friendly label and then not
                # using it is indistinguishable from never having one.
                aid = note_agent(ag_id, role, display=ag_name)
                if aid:
                    etype = 'sent_to' if role == 'sender' else 'received'
                    add_edge(aid, node_id, etype, 1.0,
                             f'{ag_name} {role} on this thread')
            # Edge to the artifact notes the thread produced (vault paths
            # in any message's `artifacts` array).
            for m in thread_msgs:
                for art in (m.get('artifacts') or []):
                    if not isinstance(art, dict): continue
                    p = (art.get('path') or '').replace('\\', '/').lstrip('/')
                    if not p: continue
                    if p in all_paths['by_path']:
                        kind = art.get('kind') or 'produced'
                        etype = 'produces' if kind in ('wrote', 'produced') else 'modified'
                        add_edge(node_id, p, etype, 0.95,
                                 f'thread artifact ({kind})')

    # ── Synthesise agent nodes from everything that referenced them ────
    for rec in agents_by_slug.values():
        meta = rec.get('meta') or {}
        roles = sorted(rec['roles'])
        # Display title: 'Selvin · Code Gremlin' when role is known, else just name.
        display = rec['title']
        if rec.get('role'):
            display = f'{display} · {rec["role"]}'
        # Tags surface role + activity context for filter syntax.
        tags = []
        if rec.get('role'): tags.append(f'role/{_re.sub(r"[^A-Za-z0-9]+", "-", rec["role"]).strip("-").lower()}')
        for r in roles: tags.append(f'activity/{r}')
        if meta.get('elevated'): tags.append('elevated')
        if meta.get('model'): tags.append(f'model/{meta["model"].split(":")[0]}')
        # mtime: agent's lastRun if available, else hiredAt — for time-scrub
        # correctness. Both fields may legitimately be strings like
        # "just hired" or "never" (they're free-form display labels in some
        # CafresoHQ states), so int() must be defensive — fall back to 0
        # whenever the field isn't a numeric timestamp.
        def _safe_ts(v):
            try: return int(v)
            except (TypeError, ValueError): return 0
        mtime = _safe_ts(meta.get('lastRun')) or _safe_ts(meta.get('hiredAt')) or 0
        node = {
            'id': rec['id'],
            'title': display,
            'path': '',
            'mtime': mtime,
            'size': 0,
            'tags': tags,
            'outlinks': 0,
            'type': 'agent',
            'source': 'hq-state',
        }
        # Attach color/meta hints the frontend can use for sprite rendering
        # without breaking the node schema (extra fields are passed through).
        if rec.get('color'): node['agentColor'] = rec['color']
        if meta.get('id'):   node['agentId']    = meta['id']
        if meta.get('model'): node['agentModel'] = meta['model']
        if meta.get('status'): node['agentStatus'] = meta['status']
        nodes_out.append(node)

    return nodes_out, edges_out


def _build_graph_rest() -> dict:
    """Use Dataview via the REST plugin to extract links + tags in one query."""
    query = (
        'TABLE WITHOUT ID '
        'file.path AS path, file.name AS title, file.size AS size, '
        'file.mtime AS mtime, file.outlinks AS outlinks, file.tags AS tags '
        'FROM "" SORT file.mtime DESC'
    )
    body = json.dumps({'query': query, 'queryType': 'dataview'}).encode('utf-8')
    s, _, raw = _cfg['obsidian_request']('POST', '/search/', body=body,
                                  content_type='application/json')
    if s != 200:
        # Fall back to FS extraction if Dataview isn't installed.
        if _cfg['vault_root']():
            return _build_graph_fs()
        raise ValueError(f'dataview query failed (status {s}); install Dataview plugin or set vault directory for FS fallback')
    try:
        data = json.loads(raw.decode('utf-8'))
    except Exception as e:
        raise ValueError(f'invalid graph response: {e}')
    rows = data if isinstance(data, list) else data.get('values', []) or data.get('rows', [])
    by_path = {}
    by_stem = {}
    raw_rows = []
    for r in rows:
        # Dataview returns objects keyed by query column names, or arrays.
        if isinstance(r, dict):
            path = r.get('path') or ''
            title = r.get('title') or pathlib.PurePosixPath(path).stem
            size = r.get('size') or 0
            mtime = r.get('mtime') or 0
            outs = r.get('outlinks') or []
            tags = r.get('tags') or []
        elif isinstance(r, list) and len(r) >= 6:
            path, title, size, mtime, outs, tags = r[:6]
        else:
            continue
        if not path: continue
        by_path[path] = True
        stem = pathlib.PurePosixPath(path).stem.lower()
        by_stem[stem] = path
        raw_rows.append((path, title, size, mtime, outs or [], tags or []))
    all_paths = {'by_path': by_path, 'by_stem': by_stem}
    nodes, edges, seen_edge = [], [], set()
    for path, title, size, mtime, outs, tags in raw_rows:
        out_paths = []
        for o in outs:
            tgt = ''
            if isinstance(o, dict):
                tgt = o.get('path') or o.get('display') or ''
            elif isinstance(o, str):
                tgt = o
            tgt = _norm_link(tgt, all_paths)
            if tgt and tgt != path:
                out_paths.append(tgt)
        clean_tags = []
        for t in tags:
            if isinstance(t, str):
                clean_tags.append(t.lstrip('#'))
        for tgt in out_paths:
            key = (path, tgt)
            if key in seen_edge: continue
            seen_edge.add(key)
            edges.append(_graph_edge_payload(path, tgt))
        # mtime from Dataview is an ISO string or a luxon DateTime serialized object.
        if isinstance(mtime, str):
            try:
                from datetime import datetime
                mtime_ms = int(datetime.fromisoformat(mtime.replace('Z','+00:00')).timestamp() * 1000)
            except Exception:
                mtime_ms = 0
        elif isinstance(mtime, (int, float)):
            mtime_ms = int(mtime)
        else:
            mtime_ms = 0
        nodes.append({
            'id': path, 'title': title or pathlib.PurePosixPath(path).stem, 'path': path,
            'mtime': mtime_ms, 'size': size or 0,
            'tags': clean_tags[:8], 'outlinks': len(out_paths),
            'type': _graph_node_type(path, clean_tags),
            'source': 'markdownvault',
        })
    indeg = {n['id']: 0 for n in nodes}
    for e in edges:
        if e['target'] in indeg:
            indeg[e['target']] += 1
    for n in nodes:
        n['inlinks'] = indeg[n['id']]
    return {'nodes': nodes, 'edges': edges}
