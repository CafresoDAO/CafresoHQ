export const idlFactory = ({ IDL }) => {
  const HqDoc = IDL.Record({
    'sha256' : IDL.Vec(IDL.Nat8),
    'body' : IDL.Vec(IDL.Nat8),
    'version' : IDL.Nat,
    'updatedAt' : IDL.Int,
  });
  const VaultMeta = IDL.Record({
    'sha256' : IDL.Vec(IDL.Nat8),
    'sealed' : IDL.Bool,
    'totalSize' : IDL.Nat,
    'version' : IDL.Nat,
    'updatedAt' : IDL.Int,
    'chunkCount' : IDL.Nat,
  });
  const DocSummary = IDL.Record({
    'sha256' : IDL.Vec(IDL.Nat8),
    'name' : IDL.Text,
    'version' : IDL.Nat,
    'updatedAt' : IDL.Int,
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
  return IDL.Service({
    'cycle_balance' : IDL.Func([], [IDL.Nat], ['query']),
    'deleteHqDoc' : IDL.Func([IDL.Text], [IDL.Bool], []),
    'deleteVault' : IDL.Func([IDL.Text], [IDL.Bool], []),
    'getHqDoc' : IDL.Func([IDL.Text], [IDL.Opt(HqDoc)], ['query']),
    'getVaultChunk' : IDL.Func(
        [IDL.Text, IDL.Nat],
        [IDL.Opt(IDL.Vec(IDL.Nat8))],
        ['query'],
      ),
    'getVaultMeta' : IDL.Func([IDL.Text], [IDL.Opt(VaultMeta)], ['query']),
    'hqVersion' : IDL.Func([], [IDL.Nat], ['query']),
    'listHqDocs' : IDL.Func([], [IDL.Vec(DocSummary)], ['query']),
    'myUsage' : IDL.Func([], [Usage], ['query']),
    'planConfigured' : IDL.Func([], [IDL.Bool], ['query']),
    'putHqDoc' : IDL.Func(
        [IDL.Text, IDL.Vec(IDL.Nat8), IDL.Vec(IDL.Nat8), IDL.Nat],
        [PutResult],
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
    'sealVault' : IDL.Func([IDL.Text, IDL.Nat], [PutResult], []),
    'setPlan' : IDL.Func([IDL.Text], [IDL.Bool], []),
    'setPlanSecret' : IDL.Func([IDL.Text], [], []),
  });
};
export const init = ({ IDL }) => { return []; };
