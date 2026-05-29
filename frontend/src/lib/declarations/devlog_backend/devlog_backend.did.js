// Hand-authored candid interface for the Dev Log backend.
// Mirrors src/backend/devlog/main.mo. `dfx generate` will regenerate this file
// automatically once the canister has been built locally.
export const idlFactory = ({ IDL }) => {
  const Author = IDL.Record({ name: IDL.Text, hue: IDL.Nat, role: IDL.Text });
  const Post = IDL.Record({
    slug: IDL.Text,
    title: IDL.Text,
    category: IDL.Text,
    layout: IDL.Text,
    author: Author,
    date: IDL.Text,
    readMin: IDL.Nat,
    excerpt: IDL.Text,
    hero: IDL.Text,
    pinned: IDL.Bool,
    body: IDL.Text,
    canister: IDL.Text,
    block: IDL.Nat,
    burned: IDL.Nat,
    tips: IDL.Nat,
    comments: IDL.Nat
  });
  const NewPostInput = IDL.Record({
    slug: IDL.Text,
    title: IDL.Text,
    category: IDL.Text,
    layout: IDL.Text,
    author: Author,
    date: IDL.Text,
    readMin: IDL.Nat,
    excerpt: IDL.Text,
    hero: IDL.Text,
    pinned: IDL.Bool,
    body: IDL.Text,
    canister: IDL.Text,
    block: IDL.Nat
  });
  const Comment = IDL.Record({
    id: IDL.Nat,
    slug: IDL.Text,
    author: Author,
    text: IDL.Text,
    burned: IDL.Nat,
    stake: IDL.Nat,
    parentId: IDL.Opt(IDL.Nat),
    createdAtNs: IDL.Nat64
  });
  const BurnReceipt = IDL.Record({
    slug: IDL.Text,
    amount: IDL.Nat,
    caller: IDL.Principal,
    block: IDL.Nat,
    atNs: IDL.Nat64
  });
  const Result = (ok) => IDL.Variant({ ok, err: IDL.Text });
  return IDL.Service({
    addAdmin: IDL.Func([IDL.Principal], [Result(IDL.Null)], []),
    upsertPost: IDL.Func([NewPostInput], [Result(Post)], []),
    postForumEntry: IDL.Func([NewPostInput], [Result(Post)], []),
    deleteForumPost: IDL.Func([IDL.Text], [Result(IDL.Null)], []),
    listPosts: IDL.Func([], [IDL.Vec(Post)], ['query']),
    listDevLogPosts: IDL.Func([], [IDL.Vec(Post)], ['query']),
    listForumPosts: IDL.Func([], [IDL.Vec(Post)], ['query']),
    getPost: IDL.Func([IDL.Text], [IDL.Opt(Post)], ['query']),
    burnTip: IDL.Func([IDL.Text, IDL.Nat], [Result(BurnReceipt)], []),
    listBurns: IDL.Func([IDL.Text], [IDL.Vec(BurnReceipt)], ['query']),
    totalBurned: IDL.Func([], [IDL.Nat], ['query']),
    postComment: IDL.Func([IDL.Text, Author, IDL.Text, IDL.Opt(IDL.Nat)], [Result(Comment)], []),
    listComments: IDL.Func([IDL.Text], [IDL.Vec(Comment)], ['query']),
    stats: IDL.Func(
      [],
      [IDL.Record({ posts: IDL.Nat, comments: IDL.Nat, burns: IDL.Nat, admins: IDL.Nat })],
      ['query']
    )
  });
};
export const init = ({ IDL }) => [];
