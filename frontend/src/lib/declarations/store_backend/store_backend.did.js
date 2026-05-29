// Hand-authored candid bindings for the Store backend.
// Regenerate with `dfx generate` once the canister has been built locally.
export const idlFactory = ({ IDL }) => {
  const Shipping = IDL.Record({
    name: IDL.Text,
    email: IDL.Text,
    street: IDL.Text,
    city: IDL.Text,
    postal: IDL.Text
  });
  const OrderItem = IDL.Record({
    slug: IDL.Text,
    qty: IDL.Nat,
    priceNanas: IDL.Nat
  });
  const OrderStatus = IDL.Variant({
    pending: IDL.Null,
    paid: IDL.Null,
    shipped: IDL.Null,
    delivered: IDL.Null,
    refunded: IDL.Null,
    cancelled: IDL.Null
  });
  const Order = IDL.Record({
    id: IDL.Nat,
    buyer: IDL.Principal,
    items: IDL.Vec(OrderItem),
    totalNanas: IDL.Nat,
    shipping: Shipping,
    status: OrderStatus,
    paidBlock: IDL.Opt(IDL.Nat),
    note: IDL.Text,
    createdAtNs: IDL.Nat64,
    updatedAtNs: IDL.Nat64
  });
  const OrderInput = IDL.Record({
    items: IDL.Vec(OrderItem),
    shipping: Shipping,
    paidBlock: IDL.Opt(IDL.Nat)
  });
  const Product = IDL.Record({
    slug: IDL.Text,
    title: IDL.Text,
    excerpt: IDL.Text,
    cat: IDL.Text,
    img: IDL.Text,
    priceNanas: IDL.Nat,
    priceCentsUSD: IDL.Nat,
    soon: IDL.Bool,
    stock: IDL.Opt(IDL.Nat),
    createdAtNs: IDL.Nat64,
    updatedAtNs: IDL.Nat64
  });
  const Stats = IDL.Record({
    products: IDL.Nat,
    orders: IDL.Nat,
    paidOrders: IDL.Nat,
    totalNanasCollected: IDL.Nat,
    admins: IDL.Nat
  });
  const Result = (ok) => IDL.Variant({ ok, err: IDL.Text });
  return IDL.Service({
    addAdmin: IDL.Func([IDL.Principal], [Result(IDL.Null)], []),
    whoAmI: IDL.Func([], [IDL.Record({ caller: IDL.Text, isAdmin: IDL.Bool })], ['query']),
    setTreasury: IDL.Func([IDL.Principal], [Result(IDL.Null)], []),
    getTreasury: IDL.Func([], [IDL.Opt(IDL.Principal)], ['query']),
    upsertProduct: IDL.Func([Product], [Result(Product)], []),
    deleteProduct: IDL.Func([IDL.Text], [Result(IDL.Null)], []),
    listProducts: IDL.Func([], [IDL.Vec(Product)], ['query']),
    getProduct: IDL.Func([IDL.Text], [IDL.Opt(Product)], ['query']),
    recordOrder: IDL.Func([OrderInput], [Result(Order)], []),
    markOrderPaid: IDL.Func([IDL.Nat, IDL.Nat], [Result(Order)], []),
    updateOrderStatus: IDL.Func([IDL.Nat, OrderStatus, IDL.Text], [Result(Order)], []),
    listMyOrders: IDL.Func([], [IDL.Vec(Order)], ['query']),
    listAllOrders: IDL.Func([], [Result(IDL.Vec(Order))], ['query']),
    getOrder: IDL.Func([IDL.Nat], [IDL.Opt(Order)], ['query']),
    stats: IDL.Func([], [Stats], ['query'])
  });
};
export const init = ({ IDL }) => [];
