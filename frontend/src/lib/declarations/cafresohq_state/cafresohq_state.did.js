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
  const MissionSchedule = IDL.Record({
    'id' : IDL.Text,
    'durationSecs' : IDL.Nat,
    'topic' : IDL.Text,
    'lastWakeResult' : IDL.Text,
    'agentId' : IDL.Text,
    'recurrence' : IDL.Text,
    'enabled' : IDL.Bool,
    'lastWakeAt' : IDL.Int,
    'updatedAt' : IDL.Int,
    'intervalSecs' : IDL.Nat,
    'nextRunAt' : IDL.Int,
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
  const LibrarySource = IDL.Record({ 'title' : IDL.Text, 'url' : IDL.Text });
  const LibraryProvenance = IDL.Record({
    'model' : IDL.Text,
    'searchEngine' : IDL.Text,
    'worker' : IDL.Opt(IDL.Principal),
    'firstSearchedAt' : IDL.Int,
    'answeredAt' : IDL.Int,
  });
  const LibraryEntry = IDL.Record({
    'id' : IDL.Text,
    'owner' : IDL.Principal,
    'q' : IDL.Text,
    'answer' : IDL.Text,
    'sources' : IDL.Vec(LibrarySource),
    'graphJson' : IDL.Text,
    'ts' : IDL.Int,
    'prov' : LibraryProvenance,
  });
  const Worker = IDL.Record({
    'principal' : IDL.Principal,
    'name' : IDL.Text,
    'status' : IDL.Text,
    'payoutOwner' : IDL.Principal,
    'payoutSubHex' : IDL.Text,
    'registeredAt' : IDL.Int,
    'approvedAt' : IDL.Int,
    'lastSeen' : IDL.Int,
    'lastAuthMs' : IDL.Int,
    'jobsDone' : IDL.Nat,
    'jobsFailed' : IDL.Nat,
    'accruedE8s' : IDL.Nat,
    'earnedE8s' : IDL.Nat,
    'updatedAt' : IDL.Int,
  });
  const WorkerPayout = IDL.Record({
    'key' : IDL.Text,
    'worker' : IDL.Principal,
    'amount' : IDL.Nat,
    'scheduledAt' : IDL.Int,
    'status' : IDL.Text,
    'blockIndex' : IDL.Opt(IDL.Nat),
    'ts' : IDL.Int,
  });
  const LibrarySummary = IDL.Record({
    'id' : IDL.Text,
    'q' : IDL.Text,
    'ts' : IDL.Int,
    'sourceCount' : IDL.Nat,
  });
  const LibraryPutResult = IDL.Variant({
    'ok' : IDL.Record({ 'id' : IDL.Text, 'existing' : IDL.Bool }),
    'err' : IDL.Text,
  });
  const OutcallHeader = IDL.Record({ 'value' : IDL.Text, 'name' : IDL.Text });
  const OutcallResponse = IDL.Record({
    'status' : IDL.Nat,
    'body' : IDL.Vec(IDL.Nat8),
    'headers' : IDL.Vec(OutcallHeader),
  });
  const OutcallTransformArgs = IDL.Record({
    'context' : IDL.Vec(IDL.Nat8),
    'response' : OutcallResponse,
  });
  return IDL.Service({
    'cycle_balance' : IDL.Func([], [IDL.Nat], ['query']),
    'deleteAgentWallet' : IDL.Func([IDL.Text], [IDL.Bool], []),
    'deleteHqDoc' : IDL.Func([IDL.Text], [IDL.Bool], []),
    'deleteMissionSchedule' : IDL.Func([IDL.Text], [IDL.Bool], []),
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
    'library_count' : IDL.Func([], [IDL.Nat], ['query']),
    'library_find' : IDL.Func([IDL.Text], [IDL.Opt(LibraryEntry)], ['query']),
    'library_get' : IDL.Func([IDL.Text], [IDL.Opt(LibraryEntry)], ['query']),
    'library_list' : IDL.Func(
        [IDL.Nat, IDL.Nat],
        [IDL.Vec(LibrarySummary)],
        ['query'],
      ),
    'library_put' : IDL.Func(
        [IDL.Text, IDL.Text, IDL.Vec(LibrarySource), IDL.Text, IDL.Text, IDL.Text],
        [LibraryPutResult],
        [],
      ),
    'library_remove' : IDL.Func([IDL.Text], [IDL.Bool], []),
    'amPlanAdmin' : IDL.Func([], [IDL.Bool], ['query']),
    'worker_register' : IDL.Func([IDL.Text, IDL.Text, IDL.Text], [IDL.Text], []),
    'worker_my_status' : IDL.Func([], [IDL.Opt(Worker)], ['query']),
    'worker_admin_list' : IDL.Func([], [IDL.Vec(Worker)], ['query']),
    'worker_admin_set_status' : IDL.Func([IDL.Principal, IDL.Text], [], []),
    'worker_payout_log' : IDL.Func([], [IDL.Vec(WorkerPayout)], ['query']),
    'search_admin_set_pay' : IDL.Func([IDL.Principal, IDL.Nat, IDL.Nat], [], []),
    'search_admin_set_budget' : IDL.Func([IDL.Nat], [], []),
    'search_pay_status' : IDL.Func(
        [],
        [IDL.Record({
          'rateE8s' : IDL.Nat, 'minE8s' : IDL.Nat,
          'ledgerSet' : IDL.Bool, 'treasurySet' : IDL.Bool, 'budgetPerDay' : IDL.Nat,
        })],
        ['query'],
      ),
    'listAgentWallets' : IDL.Func([], [IDL.Vec(AgentWallet)], ['query']),
    'listHqDocs' : IDL.Func([], [IDL.Vec(DocSummary)], ['query']),
    'listMissionSchedules' : IDL.Func(
        [],
        [IDL.Vec(MissionSchedule)],
        ['query'],
      ),
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
    'putMissionSchedule' : IDL.Func(
        [
          IDL.Text,
          IDL.Text,
          IDL.Text,
          IDL.Text,
          IDL.Nat,
          IDL.Nat,
          IDL.Bool,
          IDL.Int,
        ],
        [],
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
    'setWakeConfig' : IDL.Func([IDL.Bool, IDL.Text, IDL.Text], [], []),
    'spendPausedAll' : IDL.Func([], [IDL.Bool], ['query']),
    'wakeStatus' : IDL.Func(
        [],
        [
          IDL.Record({
            'secretSet' : IDL.Bool,
            'enabled' : IDL.Bool,
            'urlSet' : IDL.Bool,
          }),
        ],
        ['query'],
      ),
    'wakeTransform' : IDL.Func(
        [OutcallTransformArgs],
        [OutcallResponse],
        ['query'],
      ),
  });
};
export const init = ({ IDL }) => { return []; };
