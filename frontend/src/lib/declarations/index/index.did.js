export const idlFactory = ({ IDL }) => {
  const Tree = IDL.Rec();
  const TextScanResult = IDL.Record({
    'entities' : IDL.Vec(IDL.Text),
    'nextKey' : IDL.Opt(IDL.Text),
  });
  const GlobalOrder = IDL.Record({
    'id' : IDL.Int,
    'status' : IDL.Text,
    'paymentMethod' : IDL.Text,
    'timestampCreated' : IDL.Int,
    'paidBlock' : IDL.Int,
    'note' : IDL.Text,
    'shippingJson' : IDL.Text,
    'totalNanas' : IDL.Int,
    'buyer' : IDL.Text,
    'timestampUpdated' : IDL.Int,
    'itemsJson' : IDL.Text,
  });
  const Result_2 = IDL.Variant({ 'ok' : GlobalOrder, 'err' : IDL.Text });
  const ScalingSizeLimit = IDL.Variant({
    'heapSize' : IDL.Nat,
    'count' : IDL.Nat,
  });
  const ErrorCreateService = IDL.Variant({
    'InvalidPartitionKey' : IDL.Null,
    'PartitionExists' : IDL.Null,
    'NotAuthorized' : IDL.Null,
    'AnonymousCaller' : IDL.Null,
  });
  const Result_8 = IDL.Variant({ 'ok' : IDL.Text, 'err' : ErrorCreateService });
  const TransferCyclesError = IDL.Variant({
    'too_few_cycles_requested' : IDL.Null,
    'canister_quota_reached' : IDL.Null,
    'other' : IDL.Text,
    'insufficient_cycles_available' : IDL.Null,
    'aggregate_quota_reached' : IDL.Null,
  });
  const TransferCyclesResult = IDL.Variant({
    'ok' : IDL.Nat,
    'err' : TransferCyclesError,
  });
  const Color = IDL.Variant({ 'B' : IDL.Null, 'R' : IDL.Null });
  const InterCanisterActionResult = IDL.Variant({
    'ok' : IDL.Null,
    'err' : IDL.Text,
  });
  Tree.fill(
    IDL.Variant({
      'leaf' : IDL.Null,
      'node' : IDL.Tuple(
        Color,
        Tree,
        IDL.Tuple(IDL.Text, IDL.Opt(InterCanisterActionResult)),
        Tree,
      ),
    })
  );
  const CanisterCleanupStatusMap = IDL.Record({
    'stop' : Tree,
    'delete' : Tree,
    'transfer' : Tree,
  });
  const Result_4 = IDL.Variant({ 'ok' : IDL.Null, 'err' : IDL.Text });
  const Status = IDL.Variant({
    'stopped' : IDL.Null,
    'stopping' : IDL.Null,
    'running' : IDL.Null,
  });
  const CanisterId = IDL.Text;
  const CanisterSettings = IDL.Record({
    'freezing_threshold' : IDL.Opt(IDL.Nat),
    'controllers' : IDL.Opt(IDL.Vec(IDL.Principal)),
    'memory_allocation' : IDL.Opt(IDL.Nat),
    'compute_allocation' : IDL.Opt(IDL.Nat),
  });
  const IndexCanisterInformation = IDL.Record({
    'status' : Status,
    'pkCanisterMap' : IDL.Vec(IDL.Tuple(IDL.Text, IDL.Vec(CanisterId))),
    'owner' : IDL.Principal,
    'memory_size' : IDL.Nat,
    'canister_id' : IDL.Text,
    'cycles' : IDL.Nat,
    'settings' : CanisterSettings,
    'module_hash' : IDL.Opt(IDL.Vec(IDL.Nat8)),
  });
  const FrontendCanisterInformation = IDL.Record({
    'status' : Status,
    'memory_size' : IDL.Nat,
    'cycles' : IDL.Nat,
    'settings' : CanisterSettings,
    'module_hash' : IDL.Opt(IDL.Vec(IDL.Nat8)),
  });
  const LeaderRow = IDL.Record({
    'principal' : IDL.Text,
    'burnCount' : IDL.Nat,
    'totalBurned' : IDL.Int,
  });
  const PKToCanisterMapping = IDL.Vec(IDL.Tuple(IDL.Text, IDL.Vec(CanisterId)));
  const Post = IDL.Record({
    'readMin' : IDL.Int,
    'title' : IDL.Text,
    'body' : IDL.Text,
    'date' : IDL.Text,
    'hero' : IDL.Text,
    'timestampCreated' : IDL.Int,
    'slug' : IDL.Text,
    'tips' : IDL.Int,
    'authorName' : IDL.Text,
    'authorRole' : IDL.Text,
    'layout' : IDL.Text,
    'pinned' : IDL.Bool,
    'canister' : IDL.Text,
    'excerpt' : IDL.Text,
    'category' : IDL.Text,
    'authorHue' : IDL.Int,
    'block' : IDL.Int,
    'comments' : IDL.Int,
    'timestampUpdated' : IDL.Int,
    'burned' : IDL.Int,
    'authorPrincipal' : IDL.Text,
  });
  const Product = IDL.Record({
    'priceNanas' : IDL.Text,
    'name' : IDL.Text,
    'slug' : IDL.Text,
    'tags' : IDL.Vec(IDL.Text),
    'description' : IDL.Text,
    'fileKeys' : IDL.Vec(IDL.Text),
    'timestampListed' : IDL.Int,
  });
  const Treasury = IDL.Record({
    'principal' : IDL.Text,
    'timestampUpdated' : IDL.Int,
  });
  const Result_7 = IDL.Variant({
    'ok' : IDL.Vec(GlobalOrder),
    'err' : IDL.Text,
  });
  const BurnReceipt = IDL.Record({
    'id' : IDL.Int,
    'slug' : IDL.Text,
    'timestamp' : IDL.Int,
    'block' : IDL.Int,
    'caller' : IDL.Text,
    'amount' : IDL.Int,
  });
  const Comment = IDL.Record({
    'id' : IDL.Int,
    'slug' : IDL.Text,
    'text' : IDL.Text,
    'authorName' : IDL.Text,
    'authorRole' : IDL.Text,
    'stake' : IDL.Int,
    'timestamp' : IDL.Int,
    'authorHue' : IDL.Int,
    'parentId' : IDL.Int,
    'burned' : IDL.Int,
    'poster' : IDL.Text,
  });
  const Result_6 = IDL.Variant({ 'ok' : Comment, 'err' : IDL.Text });
  const Result_1 = IDL.Variant({ 'ok' : Post, 'err' : IDL.Text });
  const Result_5 = IDL.Variant({ 'ok' : BurnReceipt, 'err' : IDL.Text });
  const ErrorStopIndex = IDL.Variant({ 'NotAuthorized' : IDL.Null });
  const Result_3 = IDL.Variant({ 'ok' : IDL.Text, 'err' : ErrorStopIndex });
  const Result = IDL.Variant({ 'ok' : Product, 'err' : IDL.Text });
  const IndexCanister = IDL.Service({
    'appAutoScaleNoop' : IDL.Func([IDL.Text], [IDL.Text], []),
    'appScanKeys' : IDL.Func(
        [IDL.Text, IDL.Text, IDL.Opt(IDL.Bool)],
        [TextScanResult],
        ['query'],
      ),
    'appSkExists' : IDL.Func([IDL.Text], [IDL.Bool], ['query']),
    'appStats' : IDL.Func(
        [],
        [
          IDL.Record({
            'orders' : IDL.Nat,
            'burns' : IDL.Nat,
            'comments' : IDL.Nat,
            'posts' : IDL.Nat,
            'products' : IDL.Nat,
          }),
        ],
        ['query'],
      ),
    'autoScaleServiceCanister' : IDL.Func([IDL.Text], [IDL.Text], []),
    'callingCanisterOwnsPK' : IDL.Func(
        [IDL.Principal, IDL.Text],
        [IDL.Bool],
        [],
      ),
    'confirmOrder' : IDL.Func([IDL.Int, IDL.Int], [Result_2], []),
    'createServicePartition' : IDL.Func(
        [IDL.Text, IDL.Opt(ScalingSizeLimit)],
        [Result_8],
        [],
      ),
    'cycles_manager_transferCycles' : IDL.Func(
        [IDL.Nat],
        [TransferCyclesResult],
        [],
      ),
    'deleteCanisterMapByPK' : IDL.Func(
        [IDL.Text],
        [IDL.Opt(CanisterCleanupStatusMap)],
        [],
      ),
    'deleteForumPost' : IDL.Func([IDL.Text], [Result_4], []),
    'deleteOrphans' : IDL.Func([IDL.Vec(IDL.Text)], [IDL.Vec(IDL.Text)], []),
    'deletePost' : IDL.Func([IDL.Text], [Result_4], []),
    'deleteProduct' : IDL.Func([IDL.Text], [Result_4], []),
    'getCanisterInformation' : IDL.Func([], [IndexCanisterInformation], []),
    'getCanisterStatus' : IDL.Func(
        [IDL.Text],
        [FrontendCanisterInformation],
        [],
      ),
    'getCanistersByPK' : IDL.Func([IDL.Text], [IDL.Vec(IDL.Text)], ['query']),
    'getLeaderboard' : IDL.Func([IDL.Nat], [IDL.Vec(LeaderRow)], ['query']),
    'getNanoTimestamp' : IDL.Func([], [IDL.Int], ['query']),
    'getOrder' : IDL.Func([IDL.Int], [IDL.Opt(GlobalOrder)], ['query']),
    'getPKCount' : IDL.Func([], [IDL.Nat], ['query']),
    'getPKCountFromKeyPrefix' : IDL.Func([IDL.Text], [IDL.Int], ['query']),
    'getPKEntitiesFromKey' : IDL.Func(
        [IDL.Text],
        [IDL.Vec(IDL.Tuple(IDL.Text, IDL.Vec(IDL.Text)))],
        ['query'],
      ),
    'getPKToCanisterMapping' : IDL.Func([], [PKToCanisterMapping], ['query']),
    'getPost' : IDL.Func([IDL.Text], [IDL.Opt(Post)], ['query']),
    'getProduct' : IDL.Func([IDL.Text], [IDL.Opt(Product)], ['query']),
    'getTreasury' : IDL.Func([], [IDL.Opt(Treasury)], ['query']),
    'listAllOrders' : IDL.Func([], [Result_7], ['query']),
    'listBurns' : IDL.Func([IDL.Text], [IDL.Vec(BurnReceipt)], ['query']),
    'listComments' : IDL.Func([IDL.Text], [IDL.Vec(Comment)], ['query']),
    'listDevLogPosts' : IDL.Func([], [IDL.Vec(Post)], ['query']),
    'listForumPosts' : IDL.Func([], [IDL.Vec(Post)], ['query']),
    'listMyOrders' : IDL.Func([], [IDL.Vec(GlobalOrder)], ['query']),
    'listPosts' : IDL.Func([], [IDL.Vec(Post)], ['query']),
    'listProducts' : IDL.Func([], [IDL.Vec(Product)], ['query']),
    'load' : IDL.Func([], [IDL.Int], ['query']),
    'postComment' : IDL.Func(
        [IDL.Text, IDL.Text, IDL.Int, IDL.Text, IDL.Text, IDL.Int],
        [Result_6],
        [],
      ),
    'postForumEntry' : IDL.Func([Post], [Result_1], []),
    'pullCyclesFromService' : IDL.Func([IDL.Text], [], []),
    'pushCyclesToCanister' : IDL.Func([IDL.Text, IDL.Nat], [], []),
    'recordBurn' : IDL.Func([IDL.Text, IDL.Int, IDL.Int], [Result_5], []),
    'recordOrder' : IDL.Func(
        [IDL.Text, IDL.Text, IDL.Int, IDL.Text],
        [Result_2],
        [],
      ),
    'purchasePlanIcp' : IDL.Func([IDL.Text], [Result_2], []),
    'createCardOrder' : IDL.Func([IDL.Text], [Result_2], []),
    'confirmCardOrder' : IDL.Func([IDL.Int, IDL.Nat, IDL.Text], [Result_2], []),
    'setOraclePrincipal' : IDL.Func([IDL.Principal], [Result_4], []),
    'getOraclePrincipal' : IDL.Func([], [IDL.Text], ['query']),
    'getPlanPriceUsdCents' : IDL.Func([IDL.Text], [IDL.Opt(IDL.Nat)], ['query']),
    'setPlanPriceUsdCents' : IDL.Func([IDL.Text, IDL.Nat], [Result_4], []),
    'setHqTreasury' : IDL.Func([IDL.Principal], [Result_4], []),
    'getHqTreasury' : IDL.Func([], [IDL.Text], ['query']),
    'setTreasury' : IDL.Func([IDL.Principal], [Result_4], []),
    'stopCanister' : IDL.Func([], [Result_3], []),
    'tearDownPartition' : IDL.Func([IDL.Text], [IDL.Vec(IDL.Text)], []),
    'totalBurned' : IDL.Func([], [IDL.Int], ['query']),
    'updateOrderStatus' : IDL.Func(
        [IDL.Int, IDL.Text, IDL.Text],
        [Result_2],
        [],
      ),
    'upsertPost' : IDL.Func([Post], [Result_1], []),
    'upsertProduct' : IDL.Func([Product], [Result], []),
  });
  return IndexCanister;
};
export const init = ({ IDL }) => { return []; };
