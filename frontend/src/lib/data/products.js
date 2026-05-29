// Seed product catalog — used only as the fallback when the `store_backend`
// canister either isn't reachable or has no products yet. Once admins have
// run `upsertProduct` a few times, the canister data takes over.
//
// Shape matches what the API client returns (see `$lib/api/store.js#canisterToProduct`):
//   slug, name/title, excerpt, cat, img, price (nanas), priceCentsUSD, soon, stock
export const PRODUCTS = [
  {
    slug: 'single-origin-el-salvador',
    name: 'Single Origin · El Salvador',
    title: 'Single Origin · El Salvador',
    cat: 'coffee',
    tag: 'coffee',
    price: 3200,
    priceCentsUSD: 480,
    img: 'roaster',
    excerpt: 'Handpicked medium roast, grown on volcanic soil near San Miguel. 12oz whole bean.',
    desc: 'Handpicked medium roast, grown on volcanic soil near San Miguel. 12oz whole bean.',
    soon: false,
    stock: null
  },
  {
    slug: 'whole-bean-coffee-12-oz',
    name: 'Whole Bean Coffee · 12oz',
    title: 'Whole Bean Coffee · 12oz',
    cat: 'coffee',
    tag: 'coffee',
    price: 2800,
    priceCentsUSD: 420,
    img: 'roaster',
    excerpt: 'Our house blend. Roasted this week.',
    desc: 'Our house blend. Roasted this week.',
    soon: true,
    stock: null
  },
  {
    slug: 'cold-brew-concentrate',
    name: 'Cold Brew Concentrate',
    title: 'Cold Brew Concentrate',
    cat: 'coffee',
    tag: 'coffee',
    price: 4500,
    priceCentsUSD: 675,
    img: 'roaster',
    excerpt: 'Slow-steeped for 18 hours. Just add water.',
    desc: 'Slow-steeped for 18 hours. Just add water.',
    soon: false,
    stock: null
  },
  {
    slug: 'cafreso-tee',
    name: 'Cafreso Logo Tee',
    title: 'Cafreso Logo Tee',
    cat: 'accessories',
    tag: 'accessories',
    price: 5800,
    priceCentsUSD: 870,
    img: 'placeholder',
    excerpt: 'Soft 100% cotton. Cf script mark, screen printed in San Salvador.',
    desc: 'Soft 100% cotton. Cf script mark, screen printed in San Salvador.',
    soon: false,
    stock: null
  },
  {
    slug: 'virtual-roaster',
    name: 'Virtual Roaster · NFT',
    title: 'Virtual Roaster · NFT',
    cat: 'dao',
    tag: 'dao',
    price: 12000,
    priceCentsUSD: 1800,
    img: 'roaster',
    excerpt: 'Burn $nanas, claim a roaster, climb the leaderboard. 100% of proceeds fund the farm.',
    desc: 'Burn $nanas, claim a roaster, climb the leaderboard. 100% of proceeds fund the farm.',
    soon: false,
    stock: null
  },
  {
    slug: 'sns-neuron',
    name: 'SNS Neuron · Stake',
    title: 'SNS Neuron · Stake',
    cat: 'dao',
    tag: 'dao',
    price: 25000,
    priceCentsUSD: 3750,
    img: 'placeholder',
    excerpt: 'Lock $CF for governance voting and revenue share from the café.',
    desc: 'Lock $CF for governance voting and revenue share from the café.',
    soon: true,
    stock: null
  }
];

export function productImage(img) {
  return img === 'roaster' ? '/assets/cafreso-roaster.png' : '/assets/not-yet-available.png';
}

export function usd(nanas) {
  return (nanas * 0.0015).toFixed(2);
}

export const TAG_LABEL = { coffee: 'Coffee', dao: 'DAO', accessories: 'Merch' };
