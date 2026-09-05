#!/usr/bin/env node
/* #402 — the client's `catch` denominator, and two shape passes over it.
 *
 * Written so the NEXT hunt inherits a count instead of guessing at one.
 * Parses with @babel/parser (jsx plugin) rather than grepping: `catch`
 * appears inside comments, inside strings and inside `.catch(` chains that
 * no regex can tell apart from a real catch clause.
 *
 *   node scripts/client_catch_inventory.mjs            # the per-file table
 *   DETAIL=1 node scripts/client_catch_inventory.mjs   # + every empty body
 *   MODE=inert node scripts/client_catch_inventory.mjs # #397's runCmd shape:
 *        a try/catch wrapping an unawaited call to a locally-declared async
 *        function. `enclosingAsync=false` is the inert case — a synchronous
 *        catch cannot see a rejected promise, so the guard is structurally
 *        unable to catch the thing it names.
 *   MODE=state node scripts/client_catch_inventory.mjs # #395's nodeCount
 *        shape: useState/useRV pairs written and never read, or read and
 *        never written.
 *
 * Classification is by BODY: `empty` is {} or a comment only, `console-only`
 * is nothing but a console.* line, `surfaced` reaches a toast / setState /
 * dispatch / print, `rethrow` throws. Run it from the repo root; with no
 * arguments it sweeps every root-level .jsx plus ui/ modals/ views/ app/.
 */
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { parse } from '@babel/parser';
import _traverse from '@babel/traverse';
const traverse = _traverse.default || _traverse;

const DIRS = ['ui', 'modals', 'views', 'app'];
function clientFiles() {
  const out = [];
  for (const f of readdirSync('.')) if (f.endsWith('.jsx')) out.push(f);
  for (const d of DIRS) {
    if (!existsSync(d)) continue;
    for (const f of readdirSync(d)) if (f.endsWith('.jsx')) out.push(d + '/' + f);
  }
  return out.sort();
}
const FILES = process.argv.length > 2 ? process.argv.slice(2) : clientFiles();

function ast(f) {
  const src = readFileSync(f, 'utf8');
  try {
    return [src, parse(src, { sourceType: 'module', plugins: ['jsx'], errorRecovery: true })];
  } catch (e) { console.error('PARSE FAIL', f, e.message); return [src, null]; }
}

/* ── the inventory ───────────────────────────────────────────────────── */
function catchPass() {
  const rows = [];
  for (const f of FILES) {
    const [src, tree] = ast(f);
    if (!tree) continue;
    traverse(tree, {
      CatchClause(path) {
        const body = path.node.body.body;
        const text = src.slice(path.node.start, path.node.end);
        let cls;
        if (body.length === 0) cls = 'empty';
        else {
          const kinds = new Set();
          for (const st of body) {
            const t = src.slice(st.start, st.end);
            if (st.type === 'ThrowStatement') kinds.add('rethrow');
            else if (/^console\.(warn|error|log|debug|info)\s*\(/.test(t)) kinds.add('console');
            else kinds.add('other');
          }
          if (/cafresohqToast|Toast|toast\(|setErr|setError|Error\(|dispatchEvent|print\(|alert\(|officeCause|push\(|status|Msg|notify/i
              .test(text.slice(text.indexOf('{')))) kinds.add('surfaced');
          if (kinds.has('rethrow')) cls = 'rethrow';
          else if (kinds.has('surfaced')) cls = 'surfaced';
          else if (kinds.size === 1 && kinds.has('console')) cls = 'console-only';
          else cls = 'other';
        }
        rows.push({ file: f, line: path.node.loc.start.line, cls,
                    snippet: text.replace(/\s+/g, ' ').slice(0, 150) });
      },
    });
  }
  const order = ['empty', 'console-only', 'surfaced', 'rethrow', 'other'];
  const byFile = {};
  for (const r of rows) (byFile[r.file] ||= []).push(r);
  const tot = {};
  console.log('file\ttotal\t' + order.join('\t'));
  for (const f of Object.keys(byFile).sort()) {
    const c = Object.fromEntries(order.map(o => [o, 0]));
    for (const r of byFile[f]) { c[r.cls]++; tot[r.cls] = (tot[r.cls] || 0) + 1; }
    console.log(f + '\t' + byFile[f].length + '\t' + order.map(o => c[o]).join('\t'));
  }
  console.log('TOTAL\t' + rows.length + '\t' + order.map(o => tot[o] || 0).join('\t'));
  if (process.env.DETAIL) {
    console.log('\n--- empty + console-only detail ---');
    for (const r of rows) {
      if (r.cls === 'empty' || r.cls === 'console-only') {
        console.log(`${r.file}:${r.line}\t${r.cls}\t${r.snippet}`);
      }
    }
  }
}

/* ── guards structurally unable to catch what they name ──────────────── */
function inertPass() {
  for (const f of FILES) {
    const [, tree] = ast(f);
    if (!tree) continue;
    const asyncNames = new Set();
    traverse(tree, {
      Function(p) {
        if (!p.node.async) return;
        let name = null;
        if (p.node.id) name = p.node.id.name;
        else if (p.parent.type === 'VariableDeclarator' && p.parent.id.type === 'Identifier') name = p.parent.id.name;
        else if (p.parent.type === 'ObjectProperty' && p.parent.key.type === 'Identifier') name = p.parent.key.name;
        if (p.node.type === 'ObjectMethod' && p.node.key.type === 'Identifier') name = p.node.key.name;
        if (name) asyncNames.add(name);
      },
    });
    traverse(tree, {
      TryStatement(path) {
        if (!path.node.handler) return;
        const fn = path.getFunctionParent();
        const enclosingAsync = fn ? !!fn.node.async : false;
        path.get('block').traverse({
          CallExpression(cp) {
            if (cp.getFunctionParent() !== fn) return;
            const c = cp.node.callee;
            const nm = c.type === 'Identifier' ? c.name
              : (c.type === 'MemberExpression' && c.property.type === 'Identifier' ? c.property.name : null);
            if (cp.parentPath.isAwaitExpression()) return;
            if (cp.parentPath.isMemberExpression()
                && cp.parentPath.node.property.type === 'Identifier'
                && ['then', 'catch', 'finally'].includes(cp.parentPath.node.property.name)) return;
            if (nm && (asyncNames.has(nm) || nm === 'fetch')) {
              console.log(`${f}:${path.node.loc.start.line}\ttry-guard\tunawaited async call `
                + `${nm}() at line ${cp.node.loc.start.line}\tenclosingAsync=${enclosingAsync}`);
            }
          },
        });
      },
    });
  }
}

/* ── state written and never read (or read and never written) ────────── */
function statePass() {
  for (const f of FILES) {
    const [, tree] = ast(f);
    if (!tree) continue;
    const pairs = [];
    traverse(tree, {
      VariableDeclarator(p) {
        const id = p.node.id, init = p.node.init;
        if (!init || init.type !== 'CallExpression') return;
        const c = init.callee;
        const nm = c.type === 'Identifier' ? c.name : (c.type === 'MemberExpression' && c.property.name);
        if (!/^use(State|RV|Ref|Stored|FileStored)$/.test(nm || '')) return;
        if (id.type !== 'ArrayPattern' || id.elements.length !== 2) return;
        const [g, s] = id.elements;
        if (!g || !s || g.type !== 'Identifier' || s.type !== 'Identifier') return;
        pairs.push({ getter: g.name, setter: s.name, line: p.node.loc.start.line });
      },
    });
    const refs = {};
    traverse(tree, {
      Identifier(p) {
        if (p.parentPath.isMemberExpression() && p.parent.property === p.node && !p.parent.computed) return;
        if (p.parentPath.isObjectProperty() && p.parent.key === p.node && !p.parent.computed) return;
        refs[p.node.name] = (refs[p.node.name] || 0) + 1;
      },
      JSXIdentifier(p) { refs[p.node.name] = (refs[p.node.name] || 0) + 1; },
    });
    for (const pr of pairs) {
      const gr = (refs[pr.getter] || 0) - 1;
      const sr = (refs[pr.setter] || 0) - 1;
      if (gr === 0 && sr > 0) console.log(`${f}:${pr.line}\tWRITE-ONLY\t${pr.getter} (reads=0) / ${pr.setter} (calls=${sr})`);
      else if (sr === 0 && gr > 0) console.log(`${f}:${pr.line}\tNEVER-SET\t${pr.getter} (reads=${gr}) / ${pr.setter} (calls=0)`);
    }
  }
}

const MODE = process.env.MODE || 'catch';
if (MODE === 'inert') inertPass();
else if (MODE === 'state') statePass();
else catchPass();
