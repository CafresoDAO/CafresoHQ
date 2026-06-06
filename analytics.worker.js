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
  if (N === 0) return { nodeAttrs: {}, metrics: { nodes: 0, edges: 0 }, clusters: [], topInfluential: [], gap: null };

  // Communities (Louvain / Blondel) + modularity.
  let communities = {}, modularity = 0, communityCount = 0;
  try {
    const det = louvain.detailed(g, { getEdgeWeight: 'weight', resolution: 1 });
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

  // Cluster summaries: top nodes (by BC) per community + influence share.
  const byCommunity = {};
  let totalBc = 0;
  g.forEachNode((nd) => {
    const c = communities[nd] ?? 0;
    (byCommunity[c] = byCommunity[c] || []).push(nd);
    totalBc += bc[nd] || 0;
  });
  const clusters = Object.entries(byCommunity).map(([c, members]) => {
    const cBc = members.reduce((s, m) => s + (bc[m] || 0), 0);
    const top = members.slice().sort((a, b) => (bc[b] || 0) - (bc[a] || 0)).slice(0, 5);
    return { community: Number(c), size: members.length, share: totalBc > 0 ? cBc / totalBc : 0, topNodes: top };
  }).sort((a, b) => b.share - a.share);

  // Structure classification (biased / focused / diversified / dispersed).
  const largest = clusters.length ? Math.max(...clusters.map((c) => c.size)) : N;
  const C = largest / N;                         // share in largest community
  const E_entropy = -clusters.reduce((s, c) => s + (c.share > 0 ? c.share * Math.log(c.share) : 0), 0);
  let structure;
  if (modularity < 0.2) structure = 'biased';
  else if (modularity < 0.4) structure = 'focused';
  else if (modularity <= 0.65) structure = (C < 0.5 && E_entropy >= 1.0) ? 'diversified' : 'focused';
  else structure = 'dispersed';

  // Widest structural gap: the two largest communities with the FEWEST edges between.
  let gap = null;
  if (clusters.length >= 2) {
    const inter = {};
    g.forEachEdge((e, attr, s, t) => {
      const cs = communities[s], ct = communities[t];
      if (cs === ct) return;
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
        const score = (big[i].size + big[j].size) / (between + 1);   // big & disconnected → high
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
