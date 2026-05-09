/* ===========================================================
   Pixel sprites — human characters rendered as CSS grids.
   16×16 grid, top-down-ish 3/4 view. Each sprite has variant
   hair color + shirt color so agents are distinguishable.
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
  // shirt (c = primary, C = shade)
  c: '#888888', C: '#555555',
  // pants + shoes (fixed-ish)
  p: '#4a3a5e', P: '#2e2340',
  z: '#2b1f22',  // shoe
};

// Swap a base palette with per-character overrides.
function makePal(overrides) { return { ...PALETTE, ...overrides }; }

// 16×16 character. Rows are 16 chars each; we validate on load.
// Legend:
//  . transparent  K outline  S skin  s skin-shade  W eye-white  k pupil  m mouth
//  h hair  H hair-shade
//  c shirt  C shirt-shade
//  p pants P pants-shade  z shoe
const CHAR_16 = [
  '.....KKKKKK.....',   // 0 - top of hair
  '....KhhhhhhK....',   // 1
  '...KhHhhhhhhK...',   // 2
  '...KhHSSSSShK...',   // 3  forehead
  '..KhHSSSSSSShK..',   // 4
  '..KhSWkSSkWShK..',   // 5  eyes
  '..KSSSSSSSSSSK..',   // 6
  '..KSSSSmmSSSSK..',   // 7  mouth
  '...KSSSSSSSSK...',   // 8  chin
  '....KKSSSSKK....',   // 9  neck
  '...KcccccccK....',   // 10 shoulders
  '..KcCcccccccK...',   // 11 torso
  '..KccccccccCK...',   // 12
  '..KCccccccccK...',   // 13
  '..KppKppppKppK..',   // 14 legs split
  '..KzzK...KzzK...',   // 15 shoes
];


function render(palette) {
  // Returns a 2d array of { bg } cells by swapping palette keys.
  return CHAR_16.map(row => {
    const chars = row.split('');
    // ensure 16
    while (chars.length < 16) chars.push('.');
    return chars.slice(0, 16).map(ch => palette[ch] ? ch : '.');
  });
}

// Human sprite variants — differ in hair + shirt
const HUMANS = {
  openclaw: makePal({ h:'#4b2e1f', H:'#2a1510', c:'#8a5a9b', C:'#5e3e6c' }), // plum blazer — the CEO
  rose:     makePal({ h:'#3a2420', H:'#1e1410', c:'#e8a9a9', C:'#b36b6b' }),
  teal:     makePal({ h:'#2e1c14', H:'#15100a', c:'#7db5b5', C:'#4d8a8a' }),
  sun:      makePal({ h:'#c48a3e', H:'#7a5120', c:'#f0c674', C:'#b38a44' }),
  leaf:     makePal({ h:'#1c1410', H:'#0c0806', c:'#8bb98a', C:'#567a56' }),
  sky:      makePal({ h:'#5a3a28', H:'#331e12', c:'#89c8e0', C:'#5a98b0' }),
  mint:     makePal({ h:'#2c1a10', H:'#120804', c:'#b6e0c8', C:'#6fa890' }),
  blush:    makePal({ h:'#6a3a28', H:'#3a1c12', c:'#f3c1b2', C:'#b87866' }),
};

// 16×16 dog character — floppy ears, muzzle, nostrils.
// Uses same palette keys as CHAR_16 where possible; adds `d` for fur.
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

function Sprite({ data, scale = 3, className = '', style = {} }) {
  // `data` can be a palette key (string) or a palette object.
  const isDog = typeof data === 'string' && !!DOGS[data];
  const palette = typeof data === 'string' ? (DOGS[data] || HUMANS[data]) : data;
  const template = isDog ? CHAR_16_DOG : CHAR_16;
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
      cells.push(<div key={y+'_'+x} style={{ background: bg }} />);
    }
  }
  return <div className={`sprite pixel ${className}`} style={grid}>{cells}</div>;
}

// SPRITES map kept for back-compat with existing calls
const SPRITES = {
  openclaw: 'openclaw',
  maximus: 'maximus',
  rose: 'rose',
  teal: 'teal',
  sun: 'sun',
  leaf: 'leaf',
  sky: 'sky',
  mint: 'mint',
  blush: 'blush',
};

window.Sprite = Sprite;
window.SPRITES = SPRITES;
window.HUMANS = HUMANS;
