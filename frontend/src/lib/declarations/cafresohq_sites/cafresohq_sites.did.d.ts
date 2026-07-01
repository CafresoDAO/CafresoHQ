import type { Principal } from '@dfinity/principal';
import type { ActorMethod } from '@dfinity/agent';
import type { IDL } from '@dfinity/candid';

export type HeaderField = [string, string];
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
export interface SiteSummary {
  'fileCount' : bigint,
  'updatedAt' : bigint,
  'totalBytes' : bigint,
  'project' : string,
}
export interface _SERVICE {
  'cycle_balance' : ActorMethod<[], bigint>,
  'deleteSite' : ActorMethod<[string], bigint>,
  'http_request' : ActorMethod<[HttpRequest], HttpResponse>,
  'http_request_update' : ActorMethod<[HttpRequest], HttpResponse>,
  'listMySites' : ActorMethod<[], Array<SiteSummary>>,
  'myUsageBytes' : ActorMethod<[], bigint>,
  'putSiteFile' : ActorMethod<
    [string, string, string, Uint8Array | number[]],
    PutFileResult
  >,
}
export declare const idlFactory: IDL.InterfaceFactory;
export declare const init: (args: { IDL: typeof IDL }) => IDL.Type[];
