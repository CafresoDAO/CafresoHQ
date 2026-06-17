/**
 * print-principal.mjs — derive the oracle's principal from its seed.
 *
 *   node /opt/stripe-oracle/print-principal.mjs <SEED_HEX>
 *   # or, reading the seed from the env file:
 *   node /opt/stripe-oracle/print-principal.mjs "$(grep ^ORACLE_SEED_HEX= /etc/cafresoai/stripe-oracle.env | cut -d= -f2)"
 *
 * The principal printed here is what an admin registers on bek5d:
 *   dfx canister --network ic call index setOraclePrincipal '(principal "<PRINCIPAL>")' --identity <admin>
 *
 * Derivation matches server.js exactly (Ed25519KeyIdentity.generate(seed)), so
 * the principal is stable for a given seed.
 */
import { Ed25519KeyIdentity } from '@dfinity/identity';

const hex = (process.argv[2] || '').trim();
const m = hex.match(/.{1,2}/g);
if (!m || m.length !== 32) {
  console.error('usage: node print-principal.mjs <64-hex-char seed>  (got ' + (m ? m.length : 0) + ' bytes)');
  process.exit(1);
}
const seed = Uint8Array.from(m.map((h) => parseInt(h, 16)));
const id = Ed25519KeyIdentity.generate(seed);
console.log(id.getPrincipal().toText());
