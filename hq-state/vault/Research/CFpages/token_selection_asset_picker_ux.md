---
tags: [research, dapp-ux, token-selection, asset-picker]
---

# Token/Asset Selection & Search UX

Token selection is the gateway interaction in any swap or multichain dApp. Poor token pickers cause friction before users even commit to a transaction. Unlike traditional fintech (fixed set of assets), dApps face discovery and safety problems at scale.

## The Core UX Problem

- **Overwhelming choice**: Tens of thousands of tokens exist; showing them all breaks discoverability
- **Safety ambiguity**: Fake/scam tokens look identical to real ones without verification badges
- **Multichain confusion**: Same token symbol (USDC) exists on 5+ chains—which should I pick?
- **Stale/duplicate tokens**: Bridged, wrapped, and canonical versions of the same asset coexist
- **Mobile-hostile**: Scrolling long lists is painful on small screens

## Best Practice Pattern: "Search-First with Smart Defaults"

**Default view** (on open):
- Show user's wallet tokens first (owned tokens + recent swaps)
- If empty, show top 20 tokens by liquidity/TVL on this chain
- Recency badge ("Used 2 days ago") to surface habit

**Search flow**:
- Type-ahead as user types (name, symbol, contract address)
- Debounce to avoid re-rendering on every keystroke
- Show results grouped: "Your tokens" > "Popular" > "All results"

**Safety signals**:
- ✓ Checkmark for verified tokens (whitelisted by you, Uniswap, CoinGecko)
- ⚠ Yellow badge for wrapped versions ("USDC.e on Arbitrum")
- 🚫 Clear warning/block for known scams (Rug Radar integration, etc.)

**Chain indicator**:
- Small badge showing current network (e.g., "on Arbitrum")
- When switching chains, show "3 tokens available on Polygon, 1 requires bridge"

## Pattern: Balances & Valuation

Show wallet balance prominently:
- **Primary**: User's balance in the token (e.g., "2.5 ETH")
- **Secondary**: USD equivalent (e.g., "$8,900") for quick sanity check
- **Tertiary**: Price impact if known ("This trade would use 100% of your balance")

Don't show tokens with zero balance by default (clutter), but allow "Show all tokens" toggle.

## Pattern: Favorites & Reordering

High-frequency traders need quick access:
- Allow starring/favoriting tokens
- Show favorites at top, distinct visual treatment
- Persist favorites in localStorage (user preference, no backend needed)
- Clear default: no favorites set until user explicitly adds them

## Real-World Considerations

**Bridged tokens**: Many chains have multiple versions of the same asset:
- Native USDC (canonical from Circle)
- USDC.e (Stargate-bridged, slightly different contract)
- Wrapped USDC (bridge provider specific)

Show the canonical version by default, but allow power users to expand and see alternatives.

**Token lists**: Use public token lists to stay current:
- Uniswap token list (most tokens across chains)
- CoinGecko token list (broader coverage, less frequently curated)
- Community lists (chain-specific, niche tokens)
- Your own curated list (hand-verified for your product)

Load lists on app startup, cache locally to reduce network calls.

## Anti-Pattern: Avoid This

❌ Showing all 5,000 tokens in a single scrollable list
❌ Hiding balance information (users must guess if they have enough)
❌ No verification—let scam tokens float alongside real ones
❌ Same UI for token selection and token management (different jobs)
❌ Requiring multiple clicks to switch between chains while searching

## Implication for Cafreso

1. **Default to owned + recent tokens**, search-based discovery for others
2. **Add verification badges** (at minimum, distinguish bridged/wrapped variants)
3. **Show balances and USD values** upfront—users shouldn't have to dig
4. **Chain awareness**: When user switches chains, highlight available tokens (or "needs bridge")
5. **Mobile first**: Stacked layout, full-width search, no side-scrolling

---

Wikilinks: [[token_approval_ux_patterns]] (after selection comes approval), [[transaction_confirmation_ux]] (user confirms what they're swapping)