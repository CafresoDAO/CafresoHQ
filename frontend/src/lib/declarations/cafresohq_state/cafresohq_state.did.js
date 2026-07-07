export const idlFactory = ({ IDL }) => {
  const AgentWallet = IDL.Record({
    'token' : IDL.Text,
    'windowResetAt' : IDL.Int,
    'agentId' : IDL.Text,
    'windowSpent' : IDL.Nat,
    'updatedAt' : IDL.Int,
    'subaccountHex' : IDL.Text,
    'windowSecs' : IDL.Nat,
    'spendCap' : IDL.Nat,
    'paused' : IDL.Bool,
  });
  const HqDoc = IDL.Record({
    'sha256' : IDL.Vec(IDL.Nat8),
    'body' : IDL.Vec(IDL.Nat8),
    'version' : IDL.Nat,
    'updatedAt' : IDL.Int,
  });
  const ServiceFlag = IDL.Record({
    'enabledAt' : IDL.Int,
    'configJson' : IDL.Text,
    'enabled' : IDL.Bool,
    'updatedAt' : IDL.Int,
    'serviceId' : IDL.Text,
  });
  const VaultMeta = IDL.Record({
    'sha256' : IDL.Vec(IDL.Nat8),
    'sealed' : IDL.Bool,
    'totalSize' : IDL.Nat,
    'version' : IDL.Nat,
    'updatedAt' : IDL.Int,
    'chunkCount' : IDL.Nat,
  });
  const HeaderField = IDL.Tuple(IDL.Text, IDL.Text);
  const HttpRequest = IDL.Record({
    'url' : IDL.Text,
    'method' : IDL.Text,
    'body' : IDL.Vec(IDL.Nat8),
    'headers' : IDL.Vec(HeaderField),
  });
  const HttpResponse = IDL.Record({
    'body' : IDL.Vec(IDL.Nat8),
    'headers' : IDL.Vec(HeaderField),
    'upgrade' : IDL.Opt(IDL.Bool),
    'streaming_strategy' : IDL.Opt(IDL.Null),
    'status_code' : IDL.Nat16,
  });
  const DocSummary = IDL.Record({
    'sha256' : IDL.Vec(IDL.Nat8),
    'name' : IDL.Text,
    'version' : IDL.Nat,
    'updatedAt' : IDL.Int,
  });
  const SiteSummary = IDL.Record({
    'fileCount' : IDL.Nat,
    'updatedAt' : IDL.Int,
    'totalBytes' : IDL.Nat,
    'project' : IDL.Text,
  });
  const Payout = IDL.Record({
    'ts' : IDL.Int,
    'key' : IDL.Text,
    'status' : IDL.Text,
    'token' : IDL.Text,
    'agentId' : IDL.Text,
    'blockIndex' : IDL.Opt(IDL.Nat),
    'amount' : IDL.Nat,
    'scheduledAt' : IDL.Int,
  });
  const SalaryMode = IDL.Variant({ 'salary' : IDL.Null, 'refill' : IDL.Null });
  const Salary = IDL.Record({
    'fee' : IDL.Nat,
    'periodSecs' : IDL.Nat,
    'token' : IDL.Text,
    'active' : IDL.Bool,
    'mode' : SalaryMode,
    'stalledSince' : IDL.Opt(IDL.Int),
    'agentId' : IDL.Text,
    'lowWatermark' : IDL.Nat,
    'updatedAt' : IDL.Int,
    'ledger' : IDL.Principal,
    'nextRunAt' : IDL.Int,
    'lastResult' : IDL.Text,
    'amount' : IDL.Nat,
  });
  const WorkReceipt = IDL.Record({
    'id' : IDL.Nat,
    'ts' : IDL.Int,
    'title' : IDL.Text,
    'tool' : IDL.Text,
    'agentName' : IDL.Text,
    'agentId' : IDL.Text,
    'argHash' : IDL.Text,
    'contentSha256' : IDL.Text,
  });
  const Usage = IDL.Record({
    'quotaBytes' : IDL.Nat,
    'docBytes' : IDL.Nat,
    'plan' : IDL.Text,
    'updatedAt' : IDL.Int,
    'vaultBytes' : IDL.Nat,
    'objCount' : IDL.Nat,
  });
  const PutResult = IDL.Variant({
    'ok' : IDL.Record({ 'version' : IDL.Nat }),
    'conflict' : IDL.Record({ 'current' : IDL.Nat }),
    'quota' : IDL.Text,
  });
  const PutFileResult = IDL.Variant({
    'ok' : IDL.Record({ 'bytes' : IDL.Nat }),
    'err' : IDL.Text,
  });
  const SpendResult = IDL.Variant({
    'ok' : IDL.Record({ 'windowSpent' : IDL.Nat, 'remaining' : IDL.Nat }),
    'over' : IDL.Record({ 'cap' : IDL.Nat, 'windowSpent' : IDL.Nat }),
    'noWallet' : IDL.Null,
    'paused' : IDL.Null,
  });
  return IDL.Service({
    'cycle_balance' : IDL.Func([], [IDL.Nat], ['query']),
    'deleteAgentWallet' : IDL.Func([IDL.Text], [IDL.Bool], []),
    'deleteHqDoc' : IDL.Func([IDL.Text], [IDL.Bool], []),
    'deleteSalary' : IDL.Func([IDL.Text], [IDL.Bool], []),
    'deleteSite' : IDL.Func([IDL.Text], [IDL.Nat], []),
    'deleteVault' : IDL.Func([IDL.Text], [IDL.Bool], []),
    'getAgentWallet' : IDL.Func([IDL.Text], [IDL.Opt(AgentWallet)], ['query']),
    'getHqDoc' : IDL.Func([IDL.Text], [IDL.Opt(HqDoc)], ['query']),
    'getServiceFlag' : IDL.Func([IDL.Text], [IDL.Opt(ServiceFlag)], ['query']),
    'getSpendTotals' : IDL.Func(
        [],
        [IDL.Vec(IDL.Tuple(IDL.Text, IDL.Vec(IDL.Tuple(IDL.Text, IDL.Nat))))],
        ['query'],
      ),
    'getVaultChunk' : IDL.Func(
        [IDL.Text, IDL.Nat],
        [IDL.Opt(IDL.Vec(IDL.Nat8))],
        ['query'],
      ),
    'getVaultMeta' : IDL.Func([IDL.Text], [IDL.Opt(VaultMeta)], ['query']),
    'hqVersion' : IDL.Func([], [IDL.Nat], ['query']),
    'http_request' : IDL.Func([HttpRequest], [HttpResponse], ['query']),
    'http_request_update' : IDL.Func([HttpRequest], [HttpResponse], []),
    'listAgentWallets' : IDL.Func([], [IDL.Vec(AgentWallet)], ['query']),
    'listHqDocs' : IDL.Func([], [IDL.Vec(DocSummary)], ['query']),
    'listMySites' : IDL.Func([], [IDL.Vec(SiteSummary)], ['query']),
    'listPayouts' : IDL.Func([], [IDL.Vec(Payout)], ['query']),
    'listSalaries' : IDL.Func([], [IDL.Vec(Salary)], ['query']),
    'listServiceFlags' : IDL.Func([], [IDL.Vec(ServiceFlag)], ['query']),
    'listWorkReceipts' : IDL.Func([], [IDL.Vec(WorkReceipt)], ['query']),
    'mySiteBytes' : IDL.Func([], [IDL.Nat], ['query']),
    'myUsage' : IDL.Func([], [Usage], ['query']),
    'payrollPaused' : IDL.Func([], [IDL.Bool], ['query']),
    'planConfigured' : IDL.Func([], [IDL.Bool], ['query']),
    'putAgentWallet' : IDL.Func(
        [IDL.Text, IDL.Text, IDL.Text, IDL.Nat, IDL.Nat, IDL.Bool],
        [],
        [],
      ),
    'putHqDoc' : IDL.Func(
        [IDL.Text, IDL.Vec(IDL.Nat8), IDL.Vec(IDL.Nat8), IDL.Nat],
        [PutResult],
        [],
      ),
    'putSalary' : IDL.Func(
        [
          IDL.Text,
          IDL.Principal,
          IDL.Text,
          IDL.Nat,
          IDL.Nat,
          IDL.Nat,
          IDL.Nat,
          SalaryMode,
          IDL.Bool,
        ],
        [],
        [],
      ),
    'putServiceFlag' : IDL.Func([IDL.Text, IDL.Bool, IDL.Text], [], []),
    'putSiteFile' : IDL.Func(
        [IDL.Text, IDL.Text, IDL.Text, IDL.Vec(IDL.Nat8)],
        [PutFileResult],
        [],
      ),
    'putVaultChunk' : IDL.Func(
        [IDL.Text, IDL.Nat, IDL.Nat, IDL.Vec(IDL.Nat8)],
        [PutResult],
        [],
      ),
    'putVaultMeta' : IDL.Func(
        [IDL.Text, IDL.Nat, IDL.Nat, IDL.Vec(IDL.Nat8), IDL.Nat],
        [PutResult],
        [],
      ),
    'putWorkReceipt' : IDL.Func(
        [IDL.Text, IDL.Text, IDL.Text, IDL.Text, IDL.Text, IDL.Text],
        [IDL.Nat],
        [],
      ),
    'recordSpend' : IDL.Func([IDL.Text, IDL.Nat], [SpendResult], []),
    'runPayrollNow' : IDL.Func([IDL.Text], [IDL.Text], []),
    'sealVault' : IDL.Func([IDL.Text, IDL.Nat], [PutResult], []),
    'setAllSpendPaused' : IDL.Func([IDL.Bool], [], []),
    'setPayrollPaused' : IDL.Func([IDL.Bool], [], []),
    'setPlan' : IDL.Func([IDL.Text], [IDL.Bool], []),
    'setPlanSecret' : IDL.Func([IDL.Text], [], []),
    'spendPausedAll' : IDL.Func([], [IDL.Bool], ['query']),
  });
};
export const init = ({ IDL }) => { return []; };
