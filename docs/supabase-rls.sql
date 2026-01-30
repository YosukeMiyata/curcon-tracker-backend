-- Enable RLS for public schema tables exposed by PostgREST.
-- Public read policies are added for read-only tables used by the app.
-- Admin-only tables have RLS enabled without public policies.

-- Enable RLS
alter table public.convex_pool_history enable row level security;
alter table public.convex_pool_ohlc_daily enable row level security;
alter table public.convex_pool_remarks_history enable row level security;
alter table public.pool_latest enable row level security;
alter table public.pool_meta enable row level security;
alter table public.vault_meta enable row level security;
alter table public.token_ohlc_daily enable row level security;
alter table public.token_price_history enable row level security;
alter table public.usdjpy_history enable row level security;
alter table public.usdjpy_ohlc_daily enable row level security;
alter table public.cvx_stake_history enable row level security;
alter table public.cvx_stake_ohlc_daily enable row level security;
alter table public.cvx_crv_stake_history enable row level security;
alter table public.cvx_crv_stake_ohlc_daily enable row level security;
alter table public.simulations_history enable row level security;
alter table public.deletion_tracking_logs enable row level security;

-- Public read policies (anon/authenticated)
create policy "read convex_pool_history"
  on public.convex_pool_history
  for select
  to anon, authenticated
  using (true);

create policy "read convex_pool_ohlc_daily"
  on public.convex_pool_ohlc_daily
  for select
  to anon, authenticated
  using (true);

create policy "read convex_pool_remarks_history"
  on public.convex_pool_remarks_history
  for select
  to anon, authenticated
  using (true);

create policy "read pool_latest"
  on public.pool_latest
  for select
  to anon, authenticated
  using (true);

create policy "read pool_meta"
  on public.pool_meta
  for select
  to anon, authenticated
  using (true);

create policy "read vault_meta"
  on public.vault_meta
  for select
  to anon, authenticated
  using (true);

create policy "read token_ohlc_daily"
  on public.token_ohlc_daily
  for select
  to anon, authenticated
  using (true);

create policy "read token_price_history"
  on public.token_price_history
  for select
  to anon, authenticated
  using (true);

create policy "read usdjpy_history"
  on public.usdjpy_history
  for select
  to anon, authenticated
  using (true);

create policy "read usdjpy_ohlc_daily"
  on public.usdjpy_ohlc_daily
  for select
  to anon, authenticated
  using (true);

create policy "read cvx_stake_history"
  on public.cvx_stake_history
  for select
  to anon, authenticated
  using (true);

create policy "read cvx_stake_ohlc_daily"
  on public.cvx_stake_ohlc_daily
  for select
  to anon, authenticated
  using (true);

create policy "read cvx_crv_stake_history"
  on public.cvx_crv_stake_history
  for select
  to anon, authenticated
  using (true);

create policy "read cvx_crv_stake_ohlc_daily"
  on public.cvx_crv_stake_ohlc_daily
  for select
  to anon, authenticated
  using (true);
