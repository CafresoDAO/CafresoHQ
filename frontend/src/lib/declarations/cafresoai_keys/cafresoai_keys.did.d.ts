import type { Principal } from '@dfinity/principal';
import type { ActorMethod } from '@dfinity/agent';
import type { IDL } from '@dfinity/candid';

export interface _SERVICE {
  'cycle_balance' : ActorMethod<[], bigint>,
  'hqSessionConfigured' : ActorMethod<[], boolean>,
  'key_config' : ActorMethod<
    [],
    { 'context' : Uint8Array | number[], 'key_name' : string }
  >,
  'mintHqSession' : ActorMethod<[], { 'exp' : bigint, 'token' : string }>,
  'setHqSessionSecret' : ActorMethod<[string], undefined>,
  'vault_encrypted_key' : ActorMethod<
    [Uint8Array | number[]],
    Uint8Array | number[]
  >,
  'vault_public_key' : ActorMethod<[], Uint8Array | number[]>,
}
export declare const idlFactory: IDL.InterfaceFactory;
export declare const init: (args: { IDL: typeof IDL }) => IDL.Type[];
