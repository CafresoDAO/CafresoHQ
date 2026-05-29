import type { Principal } from '@icp-sdk/core/principal';
import type { ActorMethod } from '@icp-sdk/core/agent';
import type { IDL } from '@icp-sdk/core/candid';

export interface BurnReceipt {
  'id' : bigint,
  'slug' : string,
  'timestamp' : bigint,
  'block' : bigint,
  'caller' : string,
  'amount' : bigint,
}
export interface CanisterCleanupStatusMap {
  'stop' : Tree,
  'delete' : Tree,
  'transfer' : Tree,
}
export type CanisterId = string;
export interface CanisterSettings {
  'freezing_threshold' : [] | [bigint],
  'controllers' : [] | [Array<Principal>],
  'memory_allocation' : [] | [bigint],
  'compute_allocation' : [] | [bigint],
}
export type Color = { 'B' : null } |
  { 'R' : null };
export interface Comment {
  'id' : bigint,
  'slug' : string,
  'text' : string,
  'authorName' : string,
  'authorRole' : string,
  'stake' : bigint,
  'timestamp' : bigint,
  'authorHue' : bigint,
  'parentId' : bigint,
  'burned' : bigint,
  'poster' : string,
}
export type ErrorCreateService = { 'InvalidPartitionKey' : null } |
  { 'PartitionExists' : null } |
  { 'NotAuthorized' : null } |
  { 'AnonymousCaller' : null };
export type ErrorStopIndex = { 'NotAuthorized' : null };
export interface FrontendCanisterInformation {
  'status' : Status,
  'memory_size' : bigint,
  'cycles' : bigint,
  'settings' : CanisterSettings,
  'module_hash' : [] | [Uint8Array | number[]],
}
export interface GlobalOrder {
  'id' : bigint,
  'status' : string,
  'paymentMethod' : string,
  'timestampCreated' : bigint,
  'paidBlock' : bigint,
  'note' : string,
  'shippingJson' : string,
  'totalNanas' : bigint,
  'buyer' : string,
  'timestampUpdated' : bigint,
  'itemsJson' : string,
}
export interface IndexCanister {
  'appAutoScaleNoop' : ActorMethod<[string], string>,
  'appScanKeys' : ActorMethod<[string, string, [] | [boolean]], TextScanResult>,
  'appSkExists' : ActorMethod<[string], boolean>,
  'appStats' : ActorMethod<
    [],
    {
      'orders' : bigint,
      'burns' : bigint,
      'comments' : bigint,
      'posts' : bigint,
      'products' : bigint,
    }
  >,
  'autoScaleServiceCanister' : ActorMethod<[string], string>,
  'callingCanisterOwnsPK' : ActorMethod<[Principal, string], boolean>,
  'confirmOrder' : ActorMethod<[bigint, bigint], Result_2>,
  'createServicePartition' : ActorMethod<
    [string, [] | [ScalingSizeLimit]],
    Result_8
  >,
  'cycles_manager_transferCycles' : ActorMethod<[bigint], TransferCyclesResult>,
  'deleteCanisterMapByPK' : ActorMethod<
    [string],
    [] | [CanisterCleanupStatusMap]
  >,
  'deleteForumPost' : ActorMethod<[string], Result_4>,
  'deleteOrphans' : ActorMethod<[Array<string>], Array<string>>,
  'deletePost' : ActorMethod<[string], Result_4>,
  'deleteProduct' : ActorMethod<[string], Result_4>,
  'getCanisterInformation' : ActorMethod<[], IndexCanisterInformation>,
  'getCanisterStatus' : ActorMethod<[string], FrontendCanisterInformation>,
  'getCanistersByPK' : ActorMethod<[string], Array<string>>,
  'getLeaderboard' : ActorMethod<[bigint], Array<LeaderRow>>,
  'getNanoTimestamp' : ActorMethod<[], bigint>,
  'getOrder' : ActorMethod<[bigint], [] | [GlobalOrder]>,
  'getPKCount' : ActorMethod<[], bigint>,
  'getPKCountFromKeyPrefix' : ActorMethod<[string], bigint>,
  'getPKEntitiesFromKey' : ActorMethod<
    [string],
    Array<[string, Array<string>]>
  >,
  'getPKToCanisterMapping' : ActorMethod<[], PKToCanisterMapping>,
  'getPost' : ActorMethod<[string], [] | [Post]>,
  'getProduct' : ActorMethod<[string], [] | [Product]>,
  'getTreasury' : ActorMethod<[], [] | [Treasury]>,
  'listAllOrders' : ActorMethod<[], Result_7>,
  'listBurns' : ActorMethod<[string], Array<BurnReceipt>>,
  'listComments' : ActorMethod<[string], Array<Comment>>,
  'listDevLogPosts' : ActorMethod<[], Array<Post>>,
  'listForumPosts' : ActorMethod<[], Array<Post>>,
  'listMyOrders' : ActorMethod<[], Array<GlobalOrder>>,
  'listPosts' : ActorMethod<[], Array<Post>>,
  'listProducts' : ActorMethod<[], Array<Product>>,
  'load' : ActorMethod<[], bigint>,
  'postComment' : ActorMethod<
    [string, string, bigint, string, string, bigint],
    Result_6
  >,
  'postForumEntry' : ActorMethod<[Post], Result_1>,
  'pullCyclesFromService' : ActorMethod<[string], undefined>,
  'pushCyclesToCanister' : ActorMethod<[string, bigint], undefined>,
  'recordBurn' : ActorMethod<[string, bigint, bigint], Result_5>,
  'recordOrder' : ActorMethod<[string, string, bigint, string], Result_2>,
  'setTreasury' : ActorMethod<[Principal], Result_4>,
  'stopCanister' : ActorMethod<[], Result_3>,
  'tearDownPartition' : ActorMethod<[string], Array<string>>,
  'totalBurned' : ActorMethod<[], bigint>,
  'updateOrderStatus' : ActorMethod<[bigint, string, string], Result_2>,
  'upsertPost' : ActorMethod<[Post], Result_1>,
  'upsertProduct' : ActorMethod<[Product], Result>,
}
export interface IndexCanisterInformation {
  'status' : Status,
  'pkCanisterMap' : Array<[string, Array<CanisterId>]>,
  'owner' : Principal,
  'memory_size' : bigint,
  'canister_id' : string,
  'cycles' : bigint,
  'settings' : CanisterSettings,
  'module_hash' : [] | [Uint8Array | number[]],
}
export type InterCanisterActionResult = { 'ok' : null } |
  { 'err' : string };
export interface LeaderRow {
  'principal' : string,
  'burnCount' : bigint,
  'totalBurned' : bigint,
}
export type PKToCanisterMapping = Array<[string, Array<CanisterId>]>;
export interface Post {
  'readMin' : bigint,
  'title' : string,
  'body' : string,
  'date' : string,
  'hero' : string,
  'timestampCreated' : bigint,
  'slug' : string,
  'tips' : bigint,
  'authorName' : string,
  'authorRole' : string,
  'layout' : string,
  'pinned' : boolean,
  'canister' : string,
  'excerpt' : string,
  'category' : string,
  'authorHue' : bigint,
  'block' : bigint,
  'comments' : bigint,
  'timestampUpdated' : bigint,
  'burned' : bigint,
  'authorPrincipal' : string,
}
export interface Product {
  'priceNanas' : string,
  'name' : string,
  'slug' : string,
  'tags' : Array<string>,
  'description' : string,
  'fileKeys' : Array<string>,
  'timestampListed' : bigint,
}
export type Result = { 'ok' : Product } |
  { 'err' : string };
export type Result_1 = { 'ok' : Post } |
  { 'err' : string };
export type Result_2 = { 'ok' : GlobalOrder } |
  { 'err' : string };
export type Result_3 = { 'ok' : string } |
  { 'err' : ErrorStopIndex };
export type Result_4 = { 'ok' : null } |
  { 'err' : string };
export type Result_5 = { 'ok' : BurnReceipt } |
  { 'err' : string };
export type Result_6 = { 'ok' : Comment } |
  { 'err' : string };
export type Result_7 = { 'ok' : Array<GlobalOrder> } |
  { 'err' : string };
export type Result_8 = { 'ok' : string } |
  { 'err' : ErrorCreateService };
export type ScalingSizeLimit = { 'heapSize' : bigint } |
  { 'count' : bigint };
export type Status = { 'stopped' : null } |
  { 'stopping' : null } |
  { 'running' : null };
export interface TextScanResult {
  'entities' : Array<string>,
  'nextKey' : [] | [string],
}
export type TransferCyclesError = { 'too_few_cycles_requested' : null } |
  { 'canister_quota_reached' : null } |
  { 'other' : string } |
  { 'insufficient_cycles_available' : null } |
  { 'aggregate_quota_reached' : null };
export type TransferCyclesResult = { 'ok' : bigint } |
  { 'err' : TransferCyclesError };
export interface Treasury { 'principal' : string, 'timestampUpdated' : bigint }
export type Tree = { 'leaf' : null } |
  { 'node' : [Color, Tree, [string, [] | [InterCanisterActionResult]], Tree] };
export interface _SERVICE extends IndexCanister {}
export declare const idlFactory: IDL.InterfaceFactory;
export declare const init: (args: { IDL: typeof IDL }) => IDL.Type[];
