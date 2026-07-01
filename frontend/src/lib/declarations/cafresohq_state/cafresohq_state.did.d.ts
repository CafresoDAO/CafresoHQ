import type { Principal } from '@dfinity/principal';
import type { ActorMethod } from '@dfinity/agent';
import type { IDL } from '@dfinity/candid';

export interface AgentWallet {
  'token' : string,
  'windowResetAt' : bigint,
  'agentId' : string,
  'windowSpent' : bigint,
  'updatedAt' : bigint,
  'subaccountHex' : string,
  'windowSecs' : bigint,
  'spendCap' : bigint,
  'paused' : boolean,
}
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
export interface ServiceFlag {
  'enabledAt' : bigint,
  'configJson' : string,
  'enabled' : boolean,
  'updatedAt' : bigint,
  'serviceId' : string,
}
export type SpendResult = {
    'ok' : { 'windowSpent' : bigint, 'remaining' : bigint }
  } |
  { 'over' : { 'cap' : bigint, 'windowSpent' : bigint } } |
  { 'noWallet' : null } |
  { 'paused' : null };
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
  'deleteAgentWallet' : ActorMethod<[string], boolean>,
  'deleteHqDoc' : ActorMethod<[string], boolean>,
  'deleteVault' : ActorMethod<[string], boolean>,
  'getAgentWallet' : ActorMethod<[string], [] | [AgentWallet]>,
  'getHqDoc' : ActorMethod<[string], [] | [HqDoc]>,
  'getServiceFlag' : ActorMethod<[string], [] | [ServiceFlag]>,
  'getVaultChunk' : ActorMethod<[string, bigint], [] | [Uint8Array | number[]]>,
  'getVaultMeta' : ActorMethod<[string], [] | [VaultMeta]>,
  'hqVersion' : ActorMethod<[], bigint>,
  'listAgentWallets' : ActorMethod<[], Array<AgentWallet>>,
  'listHqDocs' : ActorMethod<[], Array<DocSummary>>,
  'listServiceFlags' : ActorMethod<[], Array<ServiceFlag>>,
  'myUsage' : ActorMethod<[], Usage>,
  'planConfigured' : ActorMethod<[], boolean>,
  'putAgentWallet' : ActorMethod<
    [string, string, string, bigint, bigint, boolean],
    undefined
  >,
  'putHqDoc' : ActorMethod<
    [string, Uint8Array | number[], Uint8Array | number[], bigint],
    PutResult
  >,
  'putServiceFlag' : ActorMethod<[string, boolean, string], undefined>,
  'putVaultChunk' : ActorMethod<
    [string, bigint, bigint, Uint8Array | number[]],
    PutResult
  >,
  'putVaultMeta' : ActorMethod<
    [string, bigint, bigint, Uint8Array | number[], bigint],
    PutResult
  >,
  'recordSpend' : ActorMethod<[string, bigint], SpendResult>,
  'sealVault' : ActorMethod<[string, bigint], PutResult>,
  'setAllSpendPaused' : ActorMethod<[boolean], undefined>,
  'setPlan' : ActorMethod<[string], boolean>,
  'setPlanSecret' : ActorMethod<[string], undefined>,
  'spendPausedAll' : ActorMethod<[], boolean>,
}
export declare const idlFactory: IDL.InterfaceFactory;
export declare const init: (args: { IDL: typeof IDL }) => IDL.Type[];
