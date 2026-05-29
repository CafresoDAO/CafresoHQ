import { Actor, HttpAgent } from '@dfinity/agent';
import { idlFactory } from './store_backend.did.js';

export function createActor(canisterId, { host, identity } = {}) {
  const agent = new HttpAgent({ host: host || 'https://icp0.io', identity });
  if (host && host.includes('127.0.0.1')) {
    agent.fetchRootKey().catch((e) => console.warn('[store] fetchRootKey failed:', e));
  }
  return Actor.createActor(idlFactory, { agent, canisterId });
}

export { idlFactory };
