---
tags: [research, dapp-ux, wallet-integration]
---

# Wallet Onboarding & Connection Patterns (2025)

## Current Market Trend: Walletless + Embedded Wallets
The industry is shifting away from mandatory browser extensions and seed phrase management. **Embedded wallets with social login** (email, Google, Apple, passkeys) are now the standard expectation for mainstream adoption. Users should never hit a "please install MetaMask" wall — it's an instant bounce.

## Critical UX Principles

**Transparency & Confidence**
- Clear transaction previews before signature requests
- Explicit warnings before signing (protect against attack phishing)
- Consistent branding/styling throughout the connection flow
- Wallets are "the gateway" — treat them as a core UI surface, not an afterthought

**Non-Custodial is Table Stakes**
- Support popular wallets natively (MetaMask, WalletConnect, etc.)
- Test wallet connections regularly — nothing drives bounce faster than failed login
- Embedded wallets should maintain non-custodial security (user keeps keys)

## Emerging Technology: Account Abstraction (ERC-4337)
- Enables **gasless transactions** — users don't pay per action
- Unlocks **social recovery** — no seed phrases, account recovery via trusted contacts
- This is the "next frontier" for removing friction

## Implication for Cafreso DApp
If the current flow requires users to install a wallet extension, it's already losing adopters. The improved version should:
1. Offer embedded/walletless login as the primary path (email/social)
2. Offer traditional wallet connection as fallback
3. If gas is a factor, explore account abstraction or zkSync/Arbitrum patterns
4. Test the end-to-end onboarding flow ruthlessly — measure bounce at each step
