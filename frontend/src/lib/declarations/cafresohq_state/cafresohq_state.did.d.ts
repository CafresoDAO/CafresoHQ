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
export type HeaderField = [string, string];
export interface HqDoc {
  'sha256' : Uint8Array | number[],
  'body' : Uint8Array | number[],
  'version' : bigint,
  'updatedAt' : bigint,
}
export interface HttpRequest {
  'url' : string,
  'method' : string,
  'body' : Uint8Array | number[],
  'headers' : Array<HeaderField>,
}
export interface HttpResponse {
  'body' : Uint8Array | number[],
  'headers' : Array<HeaderField>,
  'upgrade' : [] | [boolean],
  'streaming_strategy' : [] | [null],
  'status_code' : number,
}
export type PutFileResult = { 'ok' : { 'bytes' : bigint } } |
  { 'err' : string };
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
export interface SiteSummary {
  'fileCount' : bigint,
  'updatedAt' : bigint,
  'totalBytes' : bigint,
  'project' : string,
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
  'deleteSite' : ActorMethod<[string], bigint>,
  'deleteVault' : ActorMethod<[string], boolean>,
  'getAgentWallet' : ActorMethod<[string], [] | [AgentWallet]>,
  'getHqDoc' : ActorMethod<[string], [] | [HqDoc]>,
  'getServiceFlag' : ActorMethod<[string], [] | [ServiceFlag]>,
  'getVaultChunk' : ActorMethod<[string, bigint], [] | [Uint8Array | number[]]>,
  'getVaultMeta' : ActorMethod<[string], [] | [VaultMeta]>,
  'hqVersion' : ActorMethod<[], bigint>,
  'http_request' : ActorMethod<[HttpRequest], HttpResponse>,
  'http_request_update' : ActorMethod<[HttpRequest], HttpResponse>,
  'listAgentWallets' : ActorMethod<[], Array<AgentWallet>>,
  'listHqDocs' : ActorMethod<[], Array<DocSummary>>,
  'listMySites' : ActorMethod<[], Array<SiteSummary>>,
  'listServiceFlags' : ActorMethod<[], Array<ServiceFlag>>,
  'mySiteBytes' : ActorMethod<[], bigint>,
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
  'putSiteFile' : ActorMethod<
    [string, string, string, Uint8Array | number[]],
    PutFileResult
  >,
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
