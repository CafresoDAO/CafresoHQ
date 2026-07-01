export const idlFactory = ({ IDL }) => {
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
  const SiteSummary = IDL.Record({
    'fileCount' : IDL.Nat,
    'updatedAt' : IDL.Int,
    'totalBytes' : IDL.Nat,
    'project' : IDL.Text,
  });
  const PutFileResult = IDL.Variant({
    'ok' : IDL.Record({ 'bytes' : IDL.Nat }),
    'err' : IDL.Text,
  });
  return IDL.Service({
    'cycle_balance' : IDL.Func([], [IDL.Nat], ['query']),
    'deleteSite' : IDL.Func([IDL.Text], [IDL.Nat], []),
    'http_request' : IDL.Func([HttpRequest], [HttpResponse], ['query']),
    'http_request_update' : IDL.Func([HttpRequest], [HttpResponse], []),
    'listMySites' : IDL.Func([], [IDL.Vec(SiteSummary)], ['query']),
    'myUsageBytes' : IDL.Func([], [IDL.Nat], ['query']),
    'putSiteFile' : IDL.Func(
        [IDL.Text, IDL.Text, IDL.Text, IDL.Vec(IDL.Nat8)],
        [PutFileResult],
        [],
      ),
  });
};
export const init = ({ IDL }) => { return []; };
