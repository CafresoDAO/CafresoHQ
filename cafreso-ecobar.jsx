/* ==========================================================================
   cafreso-ecobar.jsx — the ONE ecosystem bar, three frameworks.

   A framework-agnostic Web Component (<cafreso-ecobar>) — the single source of
   truth for cross-app navigation across the Cafreso ecosystem:
       Pages (cafreso.com) · AI (ai.cafreso.com) · HQ (hq.cafreso.com) · Mine
   It replaces the two drifting copies that existed before (a Svelte
   EcosystemNav.svelte and a React EcosystemNav in app.jsx) and gives Minegold
   its first link back into the ecosystem.

   Self-contained: Shadow DOM + inline styles, no framework, no external CSS, no
   build step. Loads as a plain <script> (or a side-effect import) in any host —
   SvelteKit, the React HQ bundle, or Minegold's Vite/React — and is used as:
       <cafreso-ecobar current="hq"></cafreso-ecobar>
   Attributes:
       current = pages | ai | hq | mine   → highlights the active app (no self-link)
       compact = ""                        → icon-only brand (tight headers)
   Slot:
       <span slot="identity">…</span>      → host-provided identity chip / sign-out

   Canonical copy lives in the CafresoHQ repo; the Svelte frontend and Minegold
   load an identical copy. Editing the app list/URLs here is the single change
   point — keep the copies byte-identical.
   ========================================================================== */

(function () {
  if (typeof window === 'undefined' || !window.customElements) return;
  if (window.customElements.get('cafreso-ecobar')) return;   // idempotent across hosts

  // Single source of truth for the ecosystem. "Mine" is the canonical name for
  // the Banking.Brave / Minegold app (was inconsistently "Banking").
  var APPS = [
    { id: 'pages', label: 'Pages', url: 'https://cafreso.com',        icon: '📄', accent: '#E8A9A9' },
    { id: 'ai',    label: 'AI',    url: 'https://ai.cafreso.com',     icon: '🧠', accent: '#C9B8E0' },
    { id: 'hq',    label: 'HQ',    url: 'https://hq.cafreso.com',     icon: '🏢', accent: '#F5D25D' },
    { id: 'mine',  label: 'Mine',  url: 'https://cqyto-tiaaa-aaaau-agppa-cai.icp0.io/', icon: '⛏', accent: '#7DC9B0' },
  ];

  var CSS = '' +
    ':host{display:inline-block;font-family:Inter,system-ui,-apple-system,sans-serif;line-height:1;}' +
    '*{box-sizing:border-box;}' +
    '.bar{display:flex;align-items:center;gap:10px;}' +
    '.brand{display:flex;align-items:center;gap:8px;text-decoration:none;color:inherit;}' +
    '.dot{width:20px;height:20px;border-radius:6px;flex:0 0 auto;background:conic-gradient(from 140deg,#F5D25D,#E0A47C,#C9B8E0,#7DC9B0,#F5D25D);box-shadow:0 1px 4px rgba(0,0,0,.25);}' +
    '.word{font-weight:800;letter-spacing:.2px;font-size:14px;color:currentColor;}' +
    '.cur{font-weight:700;font-size:11px;padding:2px 7px;border-radius:20px;background:rgba(245,210,93,.16);color:#caa53a;}' +
    '.wrap{position:relative;}' +
    '.apps{cursor:pointer;border:1px solid rgba(140,128,100,.35);background:rgba(140,128,100,.10);color:currentColor;border-radius:8px;padding:5px 9px;font:600 12px Inter,system-ui,sans-serif;display:flex;align-items:center;gap:5px;}' +
    '.apps:hover{border-color:rgba(245,210,93,.5);}' +
    '.menu{position:absolute;top:calc(100% + 6px);left:0;min-width:184px;background:#1c1810;border:1px solid rgba(245,210,93,.28);border-radius:11px;padding:6px;box-shadow:0 16px 44px rgba(0,0,0,.45);z-index:9999;}' +
    '.item{display:flex;align-items:center;gap:9px;padding:8px 9px;border-radius:8px;text-decoration:none;color:#e9e2d4;font-size:13px;}' +
    '.item:hover{background:rgba(245,210,93,.12);}' +
    '.item .ic{width:20px;text-align:center;font-size:14px;}' +
    '.item .lb{flex:1;font-weight:600;}' +
    '.item .badge{font-size:9px;font-weight:700;letter-spacing:.4px;color:#9b938a;}' +
    '.item.active{cursor:default;}' +
    '.item.active .lb{color:#F5D25D;}' +
    '.dotc{width:7px;height:7px;border-radius:50%;flex:0 0 auto;}' +
    '.idslot{display:flex;align-items:center;}' +
    '::slotted(*){font-size:12px;color:inherit;}';

  function h(tag, attrs, kids) {
    var el = document.createElement(tag);
    if (attrs) for (var k in attrs) {
      if (k === 'class') el.className = attrs[k];
      else if (k === 'html') el.innerHTML = attrs[k];
      else el.setAttribute(k, attrs[k]);
    }
    (kids || []).forEach(function (c) { el.appendChild(typeof c === 'string' ? document.createTextNode(c) : c); });
    return el;
  }

  class CafresoEcobar extends HTMLElement {
    static get observedAttributes() { return ['current', 'compact']; }
    connectedCallback() { this._render(); }
    attributeChangedCallback() { if (this.shadowRoot) this._render(); }

    _render() {
      var current = (this.getAttribute('current') || '').toLowerCase();
      var compact = this.hasAttribute('compact');
      var root = this.shadowRoot || this.attachShadow({ mode: 'open' });
      root.innerHTML = '';
      root.appendChild(h('style', { html: CSS }));

      var curApp = APPS.filter(function (a) { return a.id === current; })[0];
      var bar = h('div', { class: 'bar' });

      // Brand: dot + wordmark + current-app pill.
      var brandHref = curApp ? (current === 'hq' ? 'hq.html' : curApp.url) : 'https://cafreso.com';
      var brand = h('a', { class: 'brand', href: brandHref, title: 'Cafreso' }, [h('span', { class: 'dot' })]);
      if (!compact) brand.appendChild(h('span', { class: 'word' }, ['Cafreso']));
      if (curApp) brand.appendChild(h('span', { class: 'cur' }, [curApp.label]));
      bar.appendChild(brand);

      // Apps switcher.
      var wrap = h('div', { class: 'wrap' });
      var open = false;
      var btn = h('button', { class: 'apps', 'aria-haspopup': 'true' }, ['Apps ', h('span', { class: 'caret' }, ['▾'])]);
      var menu = h('div', { class: 'menu', role: 'menu' });
      menu.style.display = 'none';
      APPS.forEach(function (a) {
        var active = a.id === current;
        var item = h(active ? 'div' : 'a', { class: 'item' + (active ? ' active' : ''), role: 'menuitem' });
        if (!active) item.setAttribute('href', a.url);
        item.appendChild(h('span', { class: 'dotc' }));
        item.lastChild.style.background = a.accent;
        item.appendChild(h('span', { class: 'ic' }, [a.icon]));
        item.appendChild(h('span', { class: 'lb' }, [a.label]));
        if (active) item.appendChild(h('span', { class: 'badge' }, ['CURRENT']));
        menu.appendChild(item);
      });
      function setOpen(v) { open = v; menu.style.display = v ? 'block' : 'none'; btn.querySelector('.caret').textContent = v ? '▴' : '▾'; }
      btn.addEventListener('click', function (e) { e.stopPropagation(); setOpen(!open); });
      document.addEventListener('click', function () { if (open) setOpen(false); });
      wrap.appendChild(btn); wrap.appendChild(menu);
      bar.appendChild(wrap);

      // Optional host identity slot (chip + sign-out).
      var idslot = h('span', { class: 'idslot' }, [h('slot', { name: 'identity' })]);
      bar.appendChild(idslot);

      root.appendChild(bar);
    }
  }

  window.customElements.define('cafreso-ecobar', CafresoEcobar);
})();
