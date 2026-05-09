export const idlFactory = ({ IDL }) => {
  return IDL.Service({
    'cycle_balance' : IDL.Func([], [IDL.Nat], ['query']),
    'key_config' : IDL.Func(
        [],
        [IDL.Record({ 'context' : IDL.Vec(IDL.Nat8), 'key_name' : IDL.Text })],
        ['query'],
      ),
    'vault_encrypted_key' : IDL.Func(
        [IDL.Vec(IDL.Nat8)],
        [IDL.Vec(IDL.Nat8)],
        [],
      ),
    'vault_public_key' : IDL.Func([], [IDL.Vec(IDL.Nat8)], []),
  });
};
export const init = ({ IDL }) => { return []; };
