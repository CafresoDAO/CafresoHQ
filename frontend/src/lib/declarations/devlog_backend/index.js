import { Actor, HttpAgent } from '@dfinity/agent';
import { idlFactory } from './devlog_backend.did.js';

/**
 * Build a Dev Log actor. `canisterId` comes from the build env (set by dfx);
 * `host` should be `http://127.0.0.1:4943` locally or `https://icp0.io` on mainnet.
 */
export function createActor(canisterId, { host, identity } = {}) {
  const agent = new HttpAgent({ host: host || 'https://icp0.io', identity });
  // Local replica certificate isn't valid — `fetchRootKey` trusts the local chain.
  if (host && host.includes('127.0.0.1')) {
    agent.fetchRootKey().catch((e) => console.warn('[devlog] fetchRootKey failed:', e));
  }
  return Actor.createActor(idlFactory, { agent, canisterId });
}

export { idlFactory };
