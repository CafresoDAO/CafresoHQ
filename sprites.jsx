/* ===========================================================
   Pixel sprites — human characters rendered as CSS grids.
   16×16 grid, top-down-ish 3/4 view. Distinct templates and
   vibes: Tailored Suits (CEO & Boss), Tech Hoodie/Headphones,
   Academic Glasses & Cardigan, Creative Wavy Scarf, Cyber Tactical.
   =========================================================== */

const PALETTE = {
  '.': 'transparent',
  K: '#2b1f22',   // outline ink
  W: '#fffaf0',   // eye highlight
  k: '#3b2e2a',   // pupil
  S: '#f3cfa9',   // skin light
  s: '#d9a97e',   // skin shade
  m: '#7a4a36',   // mouth line
  // hair colors (h = primary, H = shade)
  h: '#000000', H: '#000000',
  // shirt / jacket (c = primary, C = shade)
  c: '#888888', C: '#555555',
  // collared shirt / accent white
  w: '#ffffff',
  // tie / scarf / harness accent
  t: '#e74c3c',
  // glasses / headphones / visor
  g: '#f0c674',
  // pants + shoes
  p: '#4a3a5e', P: '#2e2340',
  z: '#2b1f22',  // shoe
};

// Swap a base palette with per-character overrides.
function makePal(overrides) { return { ...PALETTE, ...overrides }; }

/* ── 1. Classic Casual ── */
const CHAR_16 = [
  '.....KKKKKK.....',   // 0 - hair
  '....KhhhhhhK....',   // 1
  '...KhHhhhhhhK...',   // 2
  '...KhHSSSSShK...',   // 3 - forehead
  '..KhHSSSSSSShK..',   // 4
  '..KhSWkSSkWShK..',   // 5 - eyes
  '..KSSSSSSSSSSK..',   // 6
  '..KSSSSmmSSSSK..',   // 7 - mouth
  '...KSSSSSSSSK...',   // 8 - chin
  '....KKSSSSKK....',   // 9 - neck
  '...KcccccccK....',   // 10 shoulders
  '..KcCcccccccK...',   // 11 torso
  '..KccccccccCK...',   // 12
  '..KCccccccccK...',   // 13
  '..KppKppppKppK..',   // 14 legs
  '..KzzK...KzzK...',   // 15 shoes
];

/* ── 2. Tailored Suit (CEO & Boss Executive Vibe) ──
   Notch lapels, crisp white dress collar (w), sleek tie (t), tailored jacket */
const CHAR_16_SUIT = [
  '.....KKKKKK.....',   // 0 - styled hair
  '....KhhhhhhK....',   // 1
  '...KhHhhhhhhK...',   // 2 - parted hair
  '...KhHSSSSShK...',   // 3 - forehead
  '..KhHSSSSSSShK..',   // 4
  '..KhSWkSSkWShK..',   // 5 - eyes
  '..KSSSSSSSSSSK..',   // 6
  '..KSSSSmmSSSSK..',   // 7 - mouth
  '...KSSSSSSSSK...',   // 8 - chin
  '....KKwwwwKK....',   // 9 - white collared shirt (w)
  '...KccCttCccK...',   // 10 suit lapels framing tie knot (t)
  '..KcCccwtwccCcK.',   // 11 tailored suit jacket + tie trail
  '..KccccwtwccCK..',   // 12 jacket body + tie
  '..KCccccwccccK...',   // 13 buttoned jacket waist
  '..KppKppppKppK..',   // 14 pressed suit trousers
  '..KzzK...KzzK...',   // 15 polished oxfords
];

/* ── 3. Tech Hoodie (Developer / Cyberpunk / Hacker Vibe) ──
   Studio headphones (g) over ears, drawstring hood (w), kangaroo pouch */
const CHAR_16_HOODIE = [
  '.....KKKKKK.....',
  '...KKhhhhhhKK...',   // messy textured hair
  '..KhHhhhhhhHhK..',
  '..KhHSSSSSSShK..',
  '.KgKSWkSSkWShKgK',   // studio headphones (g)
  '.KgKSSSSSSSSKgK.',
  '..KgSSSSmmSSKg..',
  '...KSSSSSSSSK...',
  '....KKSSSSKK....',
  '...KccccccccK...',   // hoodie shoulders
  '..KcCccwwccCcK..',   // drawstrings (w)
  '..KccccwwcccCK..',
  '..KCccCCCCccCK..',   // kangaroo pouch
  '...KccccccccK...',
  '..KppKppppKppK..',   // denim
  '..KzzK...KzzK...',   // sneakers
];

/* ── 4. Academic / Researcher (Scholar / Scientist / Analyst Vibe) ──
   Glasses frames (g) over eyes, lab coat or cardigan over collared shirt (w) */
const CHAR_16_RESEARCHER = [
  '.....KKKKKK.....',
  '....KhhhhhhK....',
  '...KhHhhhhhhK...',
  '...KhHSSSSShK...',
  '..KhHggSSggShK..',   // glasses bridge (g)
  '..KhgkkgSgkkgShK',   // glasses frames & lenses
  '..KSSSSSSSSSSK..',
  '..KSSSSmmSSSSK..',
  '...KSSSSSSSSK...',
  '....KKwwwwKK....',   // white collared shirt (w)
  '...KccCwwCccK...',   // open cardigan / coat
  '..KcCccwwccCcK..',
  '..KccccwwcccCK..',
  '..KCccccccccCK..',
  '..KppKppppKppK..',
  '..KzzK...KzzK...',
];

/* ── 5. Creative / Designer (Artistic / Studio Vibe) ──
   Voluminous wavy hair, stylish cozy cowl scarf (t), chic sweater */
const CHAR_16_CREATIVE = [
  '....KKKKKKKK....',   // voluminous wavy hair
  '...KhhhhhhhhK...',
  '..KhHhhhhhhHhK..',
  '.KhHhhhhhhHhhhK.',
  '.KhhSWkSSkWShhK.',
  '..KhSSSSSSSSShK.',
  '..KhSSSSmmSSShK.',
  '...KhSSSSSSShK...',
  '....KKttttKK....',   // chic knit scarf (t)
  '...KcttttttccK..',
  '..KcCcccccccCcK.',   // knit sweater
  '..KccccccccccCK.',
  '..KCccccccccCK..',
  '...KccccccccK...',
  '..KppKppppKppK..',
  '..KzzK...KzzK...',
];

/* ── 6. Marketplace Contractor (Cyber Tactical / Freelancer Vibe) ──
   High-vis neon emerald tactical harness (t) & utility jacket */
const CHAR_16_MARKET = [
  '.....KKKKKK.....',
  '....KhhhhhhK....',
  '...KhHhhhhhhK...',
  '...KhHSSSSShK...',
  '..KhHSSSSSSShK..',
  '..KhSWkSSkWShK..',
  '..KSSSSSSSSSSK..',
  '..KSSSSmmSSSSK..',
  '...KSSSSSSSSK...',
  '....KKSSSSKK....',
  '...KcccttcccK...',   // neon utility straps (t)
  '..KcCcttctccCcK.',
  '..KcccttctccCK..',
  '..KCccccccccCK..',
  '..KppKppppKppK..',
  '..KzzK...KzzK...',
];

const TEMPLATES = {
  suit: CHAR_16_SUIT,
  hoodie: CHAR_16_HOODIE,
  researcher: CHAR_16_RESEARCHER,
  creative: CHAR_16_CREATIVE,
  market: CHAR_16_MARKET,
  classic: CHAR_16,
};

const humanEntry = (template, pal) => {
  const obj = Object.assign({}, pal);
  obj.template = template;
  obj.pal = pal;
  return obj;
};

// Human sprite variants — differentiated templates, clothing, hair & accessories
const HUMANS = {
  // CEO: Tailored charcoal-plum executive suit, royal gold tie, white shirt
  cafresohq: humanEntry('suit', makePal({
    h: '#4b2e1f', H: '#2a1510',
    c: '#362d42', C: '#231c2c',
    w: '#ffffff', t: '#f0c674',
    p: '#2b2436', P: '#1a1622',
    z: '#18121e'
  })),

  // BOSS: Sharp jet-black tailored three-piece suit, power crimson tie, white shirt
  boss: humanEntry('suit', makePal({
    h: '#2c2c34', H: '#181820',
    c: '#222228', C: '#141418',
    w: '#ffffff', t: '#e74c3c',
    p: '#222228', P: '#141418',
    z: '#0e0e12'
  })),

  // ROSE: Creative designer with voluminous auburn hair, warm rose sweater & amber scarf
  rose: humanEntry('creative', makePal({
    h: '#5a2c20', H: '#3a1810',
    c: '#d97c7c', C: '#a85656',
    t: '#f5c490',
    p: '#3d2d44', P: '#24192b'
  })),

  // TEAL: Cyberpunk software engineer in tech hoodie with golden headphones
  teal: humanEntry('hoodie', makePal({
    h: '#241e2c', H: '#120e18',
    c: '#2c7873', C: '#1c524e',
    w: '#d0f0ed', g: '#ffd166',
    p: '#232938', P: '#151924'
  })),

  // SUN: Business / Operations lead in tailored camel-gold blazer and white collar
  sun: humanEntry('suit', makePal({
    h: '#8b5a2b', H: '#543414',
    c: '#c68642', C: '#8f5c25',
    w: '#ffffff', t: '#2b1f22',
    p: '#3b2e2a', P: '#241b18'
  })),

  // LEAF: Researcher with stylish tortoiseshell glasses and olive academic cardigan
  leaf: humanEntry('researcher', makePal({
    h: '#28201a', H: '#140e0a',
    c: '#557a55', C: '#385238',
    w: '#f4f4ee', g: '#c48a3e',
    p: '#38302c', P: '#221c18'
  })),

  // SKY: Systems architect with modern wireframe glasses and slate-blue button-down
  sky: humanEntry('researcher', makePal({
    h: '#4a3022', H: '#281810',
    c: '#4a7c96', C: '#2e5366',
    w: '#ffffff', g: '#7db5b5',
    p: '#283244', P: '#181f2c'
  })),

  // MINT: Tech enthusiast with mint hoodie and dark purple denim
  mint: humanEntry('hoodie', makePal({
    h: '#342216', H: '#1c1008',
    c: '#4fa382', C: '#326d56',
    w: '#d2f4e8', g: '#58c8d8',
    p: '#362c44', P: '#20182c'
  })),

  // BLUSH: Community strategist with soft coral wrap and chic wavy silhouette
  blush: humanEntry('creative', makePal({
    h: '#6a3222', H: '#3c180e',
    c: '#e07a5f', C: '#b3543d',
    t: '#f2cc8f',
    p: '#3d405b', P: '#242638'
  })),

  // LAVENDER: Deep lavender chic designer with purple scarf
  lavender: humanEntry('creative', makePal({
    h: '#2e2638', H: '#1a1422',
    c: '#7b68ee', C: '#5342bf',
    t: '#e0b0ff',
    p: '#241c30', P: '#161020'
  })),

  // MARKETPLACE: Hired network contractor with high-vis emerald tactical harness
  marketplace: humanEntry('market', makePal({
    h: '#1c1c20', H: '#0c0c10',
    c: '#22262c', C: '#14171c',
    t: '#39ff14',
    p: '#1e222a', P: '#12141a',
    z: '#39ff14'
  })),
};

// 16×16 dog character — floppy ears, muzzle, nostrils.
const CHAR_16_DOG = [
  '................',  // 0 - empty
  '..KdKdddddKdK...',  // 1 - floppy ears
  '..KdKdddddKdK...',  // 2 - floppy ears
  '...KdddddddK....',  // 3 - head top
  '...KdWkddkWdK...',  // 4 - eyes
  '...KdddddddK....',  // 5
  '...KdddddddK....',  // 6
  '...KdKWWWKdK....',  // 7 - muzzle
  '...KKWkWkWKK....',  // 8 - nostrils
  '....KdWWWdK.....',  // 9 - chin
  '.....KKKKKK.....',  // 10 - neck
  '....KcccccK.....',  // 11 - collar/body
  '...KcCcccccK....',  // 12
  '..KccccccccK....',  // 13
  '..KppK...KppK...',  // 14 - legs
  '..KzzK...KzzK...',  // 15 - paws
];

// Dog sprite variants — differ only in fur color (`d` key)
const DOGS = {
  maximus: makePal({ d: '#D4903A' }),  // golden retriever
};

function renderGrid(template, palette, scale = 3, className = '', style = {}) {
  const rows = 16, cols = 16;
  const grid = {
    display: 'grid',
    gridTemplateColumns: `repeat(${cols}, ${scale}px)`,
    gridTemplateRows: `repeat(${rows}, ${scale}px)`,
    width: cols * scale,
    height: rows * scale,
    ...style,
  };
  const cells = [];
  for (let y = 0; y < rows; y++) {
    const rowStr = template[y];
    for (let x = 0; x < cols; x++) {
      const ch = rowStr[x] || '.';
      const bg = palette[ch] || 'transparent';
      cells.push(<div key={y + '_' + x} style={{ background: bg }} />);
    }
  }
  return <div className={`sprite pixel ${className}`} style={grid}>{cells}</div>;
}

function Sprite({ data, scale = 3, className = '', style = {} }) {
  // `data` can be a string key, palette object, or character spec
  const isDog = typeof data === 'string' && !!DOGS[data];
  if (isDog) {
    const palette = DOGS[data] || DOGS.maximus;
    return renderGrid(CHAR_16_DOG, palette, scale, className, style);
  }

  let entry = typeof data === 'string' ? HUMANS[data] : null;
  if (!entry) {
    if (data && typeof data === 'object') {
      entry = data.template ? data : { template: 'classic', pal: data };
    } else {
      entry = HUMANS.cafresohq;
    }
  }

  const template = TEMPLATES[entry.template] || CHAR_16;
  const palette = entry.pal || entry;
  return renderGrid(template, palette, scale, className, style);
}

// SPRITES map kept for back-compat with existing calls
const SPRITES = {
  cafresohq: 'cafresohq',
  boss: 'boss',
  maximus: 'maximus',
  rose: 'rose',
  teal: 'teal',
  sun: 'sun',
  leaf: 'leaf',
  sky: 'sky',
  mint: 'mint',
  blush: 'blush',
  lavender: 'lavender',
  marketplace: 'marketplace',
};

export { Sprite, SPRITES, HUMANS, TEMPLATES };
