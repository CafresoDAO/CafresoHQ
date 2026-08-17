/**
 * analytics.worker.js — InfraNodus-style network analysis, off the main thread.
 *
 * Bundled by esbuild into bundle/analytics-worker-<hash>.js (see build_ui_bundle.mjs)
 * and loaded by graph-engine.js as a Worker. Receives {nodes, edges}; returns
 * per-node community + betweenness + bc2 (diversity), plus graph-level metrics
 * (modularity, density, structure classification), topical clusters, top-influential
 * nodes (Jenks natural-breaks cutoff), and the widest structural gap.
 *
 * Betweenness drives node/label size; Louvain communities drive color; the gap and
 * structure class power the analytics panel — mirroring infranodus.com.
 */
import { UndirectedGraph } from 'graphology';
import louvain from 'graphology-communities-louvain';
import betweennessCentrality from 'graphology-metrics/centrality/betweenness';

// ── Jenks natural breaks: return the lower bound of the TOP class (k classes). ──
// Used to pick "top influential" nodes adaptively per-graph rather than a fixed N.
function jenksTopBreak(values, k = 3) {
  const data = values.filter((v) => v > 0).slice().sort((a, b) => a - b);
  const n = data.length;
  if (n === 0) return Infinity;
  if (n <= k) return data[0];
  // Lower-triangular matrices for variance combinations (classic Jenks).
  const mat1 = Array.from({ length: n + 1 }, () => new Array(k + 1).fill(0));
  const mat2 = Array.from({ length: n + 1 }, () => new Array(k + 1).fill(0));
  for (let i = 1; i <= k; i++) {
    mat1[1][i] = 1;
    mat2[1][i] = 0;
    for (let j = 2; j <= n; j++) mat2[j][i] = Infinity;
  }
  for (let l = 2; l <= n; l++) {
    let s1 = 0, s2 = 0, w = 0;
    for (let m = 1; m <= l; m++) {
      const i3 = l - m + 1;
      const val = data[i3 - 1];
      s2 += val * val; s1 += val; w += 1;
      const v = s2 - (s1 * s1) / w;
      const i4 = i3 - 1;
      if (i4 !== 0) {
        for (let j = 2; j <= k; j++) {
          if (mat2[l][j] >= v + mat2[i4][j - 1]) {
            mat1[l][j] = i3;
            mat2[l][j] = v + mat2[i4][j - 1];
          }
        }
      }
    }
    mat1[l][1] = 1;
    mat2[l][1] = s2 - (s1 * s1) / w;
  }
  // Walk the kth break back to the start of the top class.
  let kClass = n;
  const idx = mat1[kClass][k];
  return data[idx - 1];
}

function connectedComponentsCount(g) {
  const seen = new Set();
  let count = 0;
  g.forEachNode((node) => {
    if (seen.has(node)) return;
    count++;
    const stack = [node];
    seen.add(node);
    while (stack.length) {
      const cur = stack.pop();
      g.forEachNeighbor(cur, (nb) => { if (!seen.has(nb)) { seen.add(nb); stack.push(nb); } });
    }
  });
  return count;
}

function analyze({ nodes, edges }) {
  const g = new UndirectedGraph({ allowSelfLoops: false });
  for (const n of nodes) if (!g.hasNode(n.id)) g.addNode(n.id);
  for (const e of edges) {
    const s = e.source, t = e.target;
    if (s === t || !g.hasNode(s) || !g.hasNode(t)) continue;
    if (g.hasEdge(s, t)) g.updateEdgeAttribute(s, t, 'weight', (w) => (w || 1) + 1);
    else g.addEdge(s, t, { weight: 1 });
  }

  const N = g.order, E = g.size;
  /* An empty graph still has to answer every question the panel asks it.
     This used to return `{ nodes: 0, edges: 0 }` and nothing else, so on a
     brand-new office the panel rendered a bare "—" chip with no sentence
     under it and, worse, two labels with NOTHING after them:

         Topics:
         Separate clusters:

     which reads as a surface that failed to load rather than one with
     nothing in it yet. Zero is a real answer to "how many topics";
     undefined is not an answer at all. Same shape as `unformed` below —
     say the absence out loud instead of leaving a hole. */
  if (N === 0) {
    return {
      nodeAttrs: {},
      metrics: { nodes: 0, edges: 0, avgDegree: 0, density: 0, modularity: 0,
                 communityCount: 0, components: 0, structure: 'unformed',
                 entropy: 0, largestShare: 0, influenceCutoff: Infinity },
      clusters: [], topInfluential: [], gap: null,
    };
  }

  /* Communities (Louvain / Blondel) + modularity.

     `rng` is passed on purpose. graphology-communities-louvain defaults to
     `rng: Math.random` with `randomWalk: true`, so the partition depends on
     an unseeded draw and the same library does not get the same answer
     twice. Measured on the real office — 23 items, 22 links, nothing
     touched between runs — two hundred passes of this function returned:

         171 ×   39% · 9 items   35% · 8 items
          29 ×   43% · 10 items  30% · 7 items

     About one open in seven, the boss's Library shows a different breakdown
     of a library that did not change, and the members named under each
     topic move with it. Nothing on that panel is labelled an estimate; the
     percentages are printed to the point and the item counts are exact.

     This does not make Louvain right — it is a heuristic and both partitions
     above are defensible readings of the same graph. It makes the office
     say the same thing about the same shelf every time it is asked, which
     is the part the boss was promised. A fixed seed rather than one derived
     from the graph, so that adding one note changes the answer because the
     note changed it. */
  let communities = {}, modularity = 0, communityCount = 0;
  const seededRng = () => {
    let s = 0x9e3779b9;
    return () => {
      s = (s + 0x6d2b79f5) | 0;
      let t = Math.imul(s ^ (s >>> 15), 1 | s);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  };
  try {
    const det = louvain.detailed(g, { getEdgeWeight: 'weight', resolution: 1, rng: seededRng() });
    communities = det.communities; modularity = det.modularity; communityCount = det.count;
  } catch (_) {
    g.forEachNode((nd) => { communities[nd] = 0; });
    communityCount = 1;
  }

  // Betweenness centrality (unweighted, normalized) — structural brokers.
  let bc = {};
  try { bc = betweennessCentrality(g, { normalized: true }); }
  catch (_) { g.forEachNode((nd) => { bc[nd] = 0; }); }

  // Per-node degree + bc2 (diversity = BC / degree → "VIP" influence with few links).
  const nodeAttrs = {};
  let degSum = 0;
  g.forEachNode((nd) => {
    const deg = g.degree(nd);
    degSum += deg;
    const b = bc[nd] || 0;
    nodeAttrs[nd] = { community: communities[nd] ?? 0, betweenness: b, degree: deg, bc2: deg > 0 ? b / deg : 0 };
  });

  // Top-influential cutoff via Jenks on betweenness.
  const bcValues = Object.values(bc);
  const cut = jenksTopBreak(bcValues, 3);
  const topInfluential = Object.entries(bc)
    .filter(([, v]) => v >= cut && v > 0)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 12)
    .map(([id, v]) => ({ id, bc: v }));

  // Cluster summaries: top nodes (by BC) per community + size share.
  const byCommunity = {};
  g.forEachNode((nd) => {
    const c = communities[nd] ?? 0;
    (byCommunity[c] = byCommunity[c] || []).push(nd);
  });
  /* `share` is a SIZE share: this cluster's items over everything on the map.
     It used to be an INFLUENCE share — this cluster's betweenness over the
     graph's total — and the panel prints it immediately beside the cluster's
     own item count:

         84%  9 items
         16%  8 items
          0%  1 items
          0%  1 items
          0%  1 items

     Two numbers touching, so they get read as one quantity said twice. They
     were not. 9 items out of 23 is 39% of that map, not 84%; the reader is
     told the first topic is five times the second when they are the same
     size, and told three topics holding real work are 0% of it — on the same
     line as the count proving they are not.

     A previous pass fixed only the all-zero case (total betweenness 0, disjoint
     clusters, every share 0) and left this note in place: "Nobody reads that
     percentage as 'share of brokering' — they read it as 'how much of my
     work is this', and by that reading 0% is simply false." That reading is
     just as true when SOME clusters broker, and the mixed case is the common
     one: any office with a busy thread and a few unlinked notes.

     Nothing lost. Brokering was never named in the UI as brokering, and the
     nodes that do it are already the "Most influential" list right above.
     E_entropy below now measures spread of SIZE, which is what its verdict
     already talks about ("one dominant topic", "many scattered topics") and
     what its sibling term `C = largest / N` already measures. */
  const clusters = Object.entries(byCommunity).map(([c, members]) => {
    const top = members.slice().sort((a, b) => (bc[b] || 0) - (bc[a] || 0)).slice(0, 5);
    return { community: Number(c), size: members.length, share: members.length / N, topNodes: top };
  }).sort((a, b) => b.share - a.share);

  // Structure classification
  // (biased / overlapping / focused / diversified / dispersed).
  const largest = clusters.length ? Math.max(...clusters.map((c) => c.size)) : N;
  const C = largest / N;                         // share in largest community
  const E_entropy = -clusters.reduce((s, c) => s + (c.share > 0 ? c.share * Math.log(c.share) : 0), 0);
  /* A graph with no edges has no shape to classify, and Louvain hands back a
     NaN modularity for one. NaN is false against EVERY comparison below, so
     the chain silently fell through to its final `else` and published the
     most alarming verdict available: a brand-new office opening the Vault
     was told "Dispersed — many scattered topics, consider bridging them"
     about a cabinet holding zero notes, directly above this same panel's own
     "Topics: 1". Note that the initialiser (`modularity = 0`) would have
     said "biased" instead — also wrong, just quieter — so the default was
     never the thing keeping this honest.

     `unformed` is a real answer rather than a guess: there genuinely is not
     enough here to read a shape yet, and saying so beats picking one of four
     verdicts at random.

     The low-modularity branch is split on C for the same reason. It used to
     be `modularity < 0.2 → 'biased'` outright, and the panel prints that as
     "One dominant topic — add contrasting ideas." Measured on the real
     office, 23 items:

         Biased
         One dominant topic — add contrasting ideas.
         ...
         Topics: 8
         Main topics
           39%  9 items
           35%  8 items
            4%  1 item   (×3)

     Nothing dominates 39% of a map, and the panel says so itself four lines
     below the sentence claiming it does. Low modularity does not mean one
     topic owns the map — it means the topics are not cleanly SEPARATED, and
     this office's shape is why: two hubs (the boss and the one coworker)
     sharing seven of their leaves, so seven of twenty-two links cross the
     boundary. Two topics of near-equal size, heavily interleaved.

     C = largest / N is the number that actually measures dominance and it
     was already sitting right here, computed and unread by this branch. The
     half-the-map line is not a new constant — the `diversified` branch below
     already draws dominance there — but the comparison is strict, and that
     matters at the boundary: a map split into two topics of six is C = 0.5
     exactly, and "one dominant topic" over two equal halves is the same lie
     this fix is for, just smaller. Strict, the rule survives being said out
     loud: one topic dominates when it holds more of the map than every other
     topic put together. Above that line the advice on the chip is worth
     taking. Below it the honest reading is the one the shape supports — the
     topics run together. */
  let structure;
  if (!Number.isFinite(modularity) || E === 0 || N < 3) structure = 'unformed';
  else if (modularity < 0.2) structure = (C > 0.5) ? 'biased' : 'overlapping';
  else if (modularity < 0.4) structure = 'focused';
  else if (modularity <= 0.65) structure = (C < 0.5 && E_entropy >= 1.0) ? 'diversified' : 'focused';
  else structure = 'dispersed';

  /* Widest structural gap: the two largest communities with the FEWEST edges
     between. The panel prints this as "Weakly connected: A ⟷ B", which is an
     ABSOLUTE claim — so it may only be emitted when the pair really is weakly
     connected. It used to be emitted whenever there were two clusters at all,
     because `score` only ranks pairs RELATIVELY and there is always a worst
     pair, so the alert could never not fire. Two measured consequences:

       · Two triangles joined by SIX cross edges — about as connected as two
         groups get — were reported as "Weakly connected".
       · Three notes with no links at all produced "Weakly connected: a ⟷ b"
         in a pink alert box directly beneath the structure chip's own
         "Not enough here to read a shape yet". One panel, one render,
         contradicting itself — the same fault as the NaN fall-through above,
         one section further down.

     Four gates now. `structure === 'unformed'` kills it outright: a graph
     with no shape cannot have a gap in its shape. Both sides must hold at
     least two items, because a gap is a missing bridge between two bodies of
     work and one orphan item is not a body of work: measured on the real
     office (6 items, 2 links) the pick was "Weakly connected: Llama ⟷
     Hermes", where Hermes is simply an unused coworker sitting alone. True,
     and useless — everything is weakly connected to an orphan.

     And the pair must be sparsely joined by BOTH readings of the word,
     because the first one alone compares a count of links against a count of
     items and the units do not match. The bar rises with the size of the
     smaller group while the crossing count does not, so two big topics stay
     under it however heavily they are joined. Measured on the real office,
     23 items, one render:

         Overlapping
         Topics blur into each other — plenty of links cross between them.
         ...
         Structural gap
         Weakly connected: Local Brain · Generalist ⟷ You (boss)

     Those two topics hold 8 and 7 links inside themselves and are joined by
     7 — seven of the map's twenty-two links, nearly a third of everything
     the office knows, running between exactly the pair being called weakly
     connected. The panel said "plenty of links cross between them" and then
     said the opposite four lines down.

     So a pair also has to carry fewer links across it than either side holds
     inside itself. Links against links — and it says out loud without
     flinching: these two topics have less holding them together than either
     of them has holding itself together. Ranking among qualifying pairs is
     unchanged. */
  let gap = null;
  if (clusters.length >= 2 && structure !== 'unformed') {
    const inter = {}, intra = {};
    g.forEachEdge((e, attr, s, t) => {
      const cs = communities[s], ct = communities[t];
      if (cs === ct) { intra[cs] = (intra[cs] || 0) + 1; return; }
      const key = cs < ct ? cs + '|' + ct : ct + '|' + cs;
      inter[key] = (inter[key] || 0) + 1;
    });
    const big = clusters.slice(0, 5);
    let best = null;
    for (let i = 0; i < big.length; i++) {
      for (let j = i + 1; j < big.length; j++) {
        const a = big[i].community, b = big[j].community;
        const key = a < b ? a + '|' + b : b + '|' + a;
        const between = inter[key] || 0;
        if (big[i].size < 2 || big[j].size < 2) continue;              // an orphan is not a topic
        if (between >= Math.min(big[i].size, big[j].size)) continue;   // genuinely joined — not a gap
        // …and joined by fewer links than either side holds inside itself.
        if (between >= Math.min(intra[a] || 0, intra[b] || 0)) continue;
        const score = (big[i].size + big[j].size) / (between + 1);     // big & disconnected → high
        if (!best || score > best.score) best = { a, b, between, score, aTop: big[i].topNodes[0], bTop: big[j].topNodes[0] };
      }
    }
    gap = best;
  }

  const metrics = {
    nodes: N, edges: E,
    avgDegree: N ? degSum / N : 0,
    density: N > 1 ? (2 * E) / (N * (N - 1)) : 0,
    modularity, communityCount,
    components: connectedComponentsCount(g),
    structure, entropy: E_entropy,
    largestShare: C,
    influenceCutoff: cut,
  };

  return { nodeAttrs, metrics, clusters, topInfluential, gap };
}

self.onmessage = (ev) => {
  const { id, nodes, edges } = ev.data || {};
  try {
    const result = analyze({ nodes: nodes || [], edges: edges || [] });
    self.postMessage({ id, ok: true, ...result });
  } catch (e) {
    self.postMessage({ id, ok: false, error: String(e && e.message || e) });
  }
};
