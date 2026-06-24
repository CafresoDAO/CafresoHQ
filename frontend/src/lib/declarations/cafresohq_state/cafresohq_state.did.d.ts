import type { Principal } from '@dfinity/principal';
import type { ActorMethod } from '@dfinity/agent';
import type { IDL } from '@dfinity/candid';

export interface DocSummary {
  'sha256' : Uint8Array | number[],
  'name' : string,
  'version' : bigint,
  'updatedAt' : bigint,
}
export interface HqDoc {
  'sha256' : Uint8Array | number[],
  'body' : Uint8Array | number[],
  'version' : bigint,
  'updatedAt' : bigint,
}
export type PutResult = { 'ok' : { 'version' : bigint } } |
  { 'conflict' : { 'current' : bigint } } |
  { 'quota' : string };
export interface Usage {
  'quotaBytes' : bigint,
  'docBytes' : bigint,
  'plan' : string,
  'updatedAt' : bigint,
  'vaultBytes' : bigint,
  'objCount' : bigint,
}
export interface VaultMeta {
  'sha256' : Uint8Array | number[],
  'sealed' : boolean,
  'totalSize' : bigint,
  'version' : bigint,
  'updatedAt' : bigint,
  'chunkCount' : bigint,
}
export interface _SERVICE {
  'cycle_balance' : ActorMethod<[], bigint>,
  'deleteHqDoc' : ActorMethod<[string], boolean>,
  'deleteVault' : ActorMethod<[string], boolean>,
  'getHqDoc' : ActorMethod<[string], [] | [HqDoc]>,
  'getVaultChunk' : ActorMethod<[string, bigint], [] | [Uint8Array | number[]]>,
  'getVaultMeta' : ActorMethod<[string], [] | [VaultMeta]>,
  'hqVersion' : ActorMethod<[], bigint>,
  'listHqDocs' : ActorMethod<[], Array<DocSummary>>,
  'myUsage' : ActorMethod<[], Usage>,
  'planConfigured' : ActorMethod<[], boolean>,
  'putHqDoc' : ActorMethod<
    [string, Uint8Array | number[], Uint8Array | number[], bigint],
    PutResult
  >,
  'putVaultChunk' : ActorMethod<
    [string, bigint, bigint, Uint8Array | number[]],
    PutResult
  >,
  'putVaultMeta' : ActorMethod<
    [string, bigint, bigint, Uint8Array | number[], bigint],
    PutResult
  >,
  'sealVault' : ActorMethod<[string, bigint], PutResult>,
  'setPlan' : ActorMethod<[string], boolean>,
  'setPlanSecret' : ActorMethod<[string], undefined>,
}
export declare const idlFactory: IDL.InterfaceFactory;
export declare const init: (args: { IDL: typeof IDL }) => IDL.Type[];
