-- Supabase schema for DynamoDB migration
-- Uses snake_case table and column names.

-- Convex pool history (hourly)
create table if not exists convex_pool_history (
  pool_id text not null,
  timestamp timestamptz not null,
  timezone text,
  pool_name text,
  factory_id text,
  current_vapr text,
  projected_vapr text,
  tvl text,
  vecrv_boost text,
  remarks text,
  current_vapr_numeric numeric,
  projected_vapr_numeric numeric,
  tvl_numeric numeric,
  vecrv_boost_numeric numeric,
  data_source text,
  datetime timestamptz,
  created_at timestamptz,
  primary key (pool_id, timestamp)
);
create index if not exists idx_convex_pool_history_timestamp
  on convex_pool_history (timestamp desc);

-- Convex pool OHLC (daily)
create table if not exists convex_pool_ohlc_daily (
  pool_id_type text not null,
  timestamp timestamptz not null,
  timezone text,
  pool_name text,
  pool_id text,
  factory_id text,
  type text,
  open numeric,
  high numeric,
  low numeric,
  close numeric,
  sample_count integer,
  data_source text,
  datetime timestamptz,
  created_at timestamptz,
  primary key (pool_id_type, timestamp)
);
create index if not exists idx_convex_pool_ohlc_daily_timestamp
  on convex_pool_ohlc_daily (timestamp desc);

-- Convex pool remarks history
create table if not exists convex_pool_remarks_history (
  pool_id text not null,
  timestamp timestamptz not null,
  timezone text,
  pool_name text,
  factory_id text,
  remarks text,
  data_source text,
  datetime timestamptz,
  created_at timestamptz,
  primary key (pool_id, timestamp)
);
create index if not exists idx_convex_pool_remarks_history_timestamp
  on convex_pool_remarks_history (timestamp desc);

-- Convex failed pool matching (factory_id 未マッチのプール記録、GitHub Actions + Supabase 運用用)
create table if not exists convex_failed_pool_matching (
  pool_name text primary key,
  token_symbols jsonb default '[]',
  first_seen timestamptz,
  last_seen timestamptz,
  failure_count integer default 0,
  status text default 'pending',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);
create index if not exists idx_convex_failed_pool_matching_status
  on convex_failed_pool_matching (status);

-- cvxCRV stake history
create table if not exists cvx_crv_stake_history (
  stake text not null,
  timestamp timestamptz not null,
  timezone text,
  pool text,
  max_vapr_gov_token_rewards text,
  max_vapr_stablecoin_rewards text,
  tvl text,
  max_vapr_gov_numeric numeric,
  max_vapr_stable_numeric numeric,
  tvl_numeric numeric,
  data_source text,
  datetime timestamptz,
  created_at timestamptz,
  primary key (stake, timestamp)
);
create index if not exists idx_cvx_crv_stake_history_timestamp
  on cvx_crv_stake_history (timestamp desc);

-- cvxCRV stake OHLC (daily)
create table if not exists cvx_crv_stake_ohlc_daily (
  type text not null,
  timestamp timestamptz not null,
  timezone text,
  pool text,
  stake text,
  open numeric,
  high numeric,
  low numeric,
  close numeric,
  sample_count integer,
  data_source text,
  datetime timestamptz,
  created_at timestamptz,
  primary key (type, timestamp)
);
create index if not exists idx_cvx_crv_stake_ohlc_daily_timestamp
  on cvx_crv_stake_ohlc_daily (timestamp desc);

-- CVX stake history
create table if not exists cvx_stake_history (
  token text not null,
  timestamp timestamptz not null,
  timezone text,
  vapr text,
  tvl text,
  vapr_numeric numeric,
  tvl_numeric numeric,
  data_source text,
  datetime timestamptz,
  created_at timestamptz,
  primary key (token, timestamp)
);
create index if not exists idx_cvx_stake_history_timestamp
  on cvx_stake_history (timestamp desc);

-- CVX stake OHLC (daily)
create table if not exists cvx_stake_ohlc_daily (
  type text not null,
  timestamp timestamptz not null,
  timezone text,
  token text,
  open numeric,
  high numeric,
  low numeric,
  close numeric,
  sample_count integer,
  data_source text,
  datetime timestamptz,
  created_at timestamptz,
  primary key (type, timestamp)
);
create index if not exists idx_cvx_stake_ohlc_daily_timestamp
  on cvx_stake_ohlc_daily (timestamp desc);

-- Deletion tracking logs
create table if not exists deletion_tracking_logs (
  log_id text not null,
  timestamp timestamptz not null,
  additional_data jsonb,
  caller_info jsonb,
  created_at timestamptz,
  date date,
  function_name text,
  log_level text,
  operation_type text,
  source text,
  status text,
  table_name text,
  primary key (log_id, timestamp)
);
create index if not exists idx_deletion_tracking_logs_table_name
  on deletion_tracking_logs (table_name);
create index if not exists idx_deletion_tracking_logs_operation_type
  on deletion_tracking_logs (operation_type);
create index if not exists idx_deletion_tracking_logs_date
  on deletion_tracking_logs (date);

-- Pool latest
create table if not exists pool_latest (
  pool_id text primary key,
  timezone text,
  timestamp timestamptz,
  pool_name text,
  current_vapr text,
  projected_vapr text,
  tvl text,
  vecrv_boost text,
  remarks text,
  current_vapr_numeric numeric,
  projected_vapr_numeric numeric,
  tvl_numeric numeric,
  data_source text,
  is_vault boolean,
  updated_at timestamptz,
  token_symbols text[],
  factory_id text,
  search_tokens text[],
  normalized_name text
);
create index if not exists idx_pool_latest_timestamp
  on pool_latest (timestamp desc);

-- Pool meta (raw jsonb + common fields)
create table if not exists pool_meta (
  pool_id text primary key,
  name text,
  symbol text,
  timezone text,
  timestamp timestamptz,
  data_source text,
  datetime timestamptz,
  created_at timestamptz,
  updated_at timestamptz,
  raw jsonb
);

-- Simulations history (TTL: 30 days handled by job)
create table if not exists simulations_history (
  pool_id text not null,
  timestamp timestamptz not null,
  created_at timestamptz,
  data_source text,
  datetime timestamptz,
  diagnostics jsonb,
  expires_at bigint,
  factory_id text,
  pool text,
  request jsonb,
  result jsonb,
  simulation_id text,
  status text,
  timezone text,
  primary key (pool_id, timestamp)
);
create index if not exists idx_simulations_history_timestamp
  on simulations_history (timestamp desc);
create index if not exists idx_simulations_history_expires_at
  on simulations_history (expires_at);

-- Token OHLC (daily)
create table if not exists token_ohlc_daily (
  token text not null,
  timestamp timestamptz not null,
  timezone text,
  open numeric,
  high numeric,
  low numeric,
  close numeric,
  sample_count integer,
  data_source text,
  datetime timestamptz,
  created_at timestamptz,
  primary key (token, timestamp)
);
create index if not exists idx_token_ohlc_daily_timestamp
  on token_ohlc_daily (timestamp desc);

-- Token price history
create table if not exists token_price_history (
  token text not null,
  timestamp timestamptz not null,
  timezone text,
  price text,
  price_numeric numeric,
  pool_count integer,
  pools text,
  factory_ids text,
  data_source text,
  datetime timestamptz,
  created_at timestamptz,
  primary key (token, timestamp)
);
create index if not exists idx_token_price_history_timestamp
  on token_price_history (timestamp desc);

-- USD/JPY history
create table if not exists usdjpy_history (
  asset text not null,
  timestamp timestamptz not null,
  timezone text,
  rate numeric,
  source text,
  datetime timestamptz,
  created_at timestamptz,
  primary key (asset, timestamp)
);
create index if not exists idx_usdjpy_history_timestamp
  on usdjpy_history (timestamp desc);

-- USD/JPY OHLC (daily)
create table if not exists usdjpy_ohlc_daily (
  asset text not null,
  timestamp timestamptz not null,
  timezone text,
  open numeric,
  high numeric,
  low numeric,
  close numeric,
  sample_count integer,
  data_source text,
  datetime timestamptz,
  created_at timestamptz,
  primary key (asset, timestamp)
);
create index if not exists idx_usdjpy_ohlc_daily_timestamp
  on usdjpy_ohlc_daily (timestamp desc);

-- Vault meta (raw jsonb + common fields)
create table if not exists vault_meta (
  vault_id text primary key,
  name text,
  timezone text,
  timestamp timestamptz,
  data_source text,
  datetime timestamptz,
  created_at timestamptz,
  updated_at timestamptz,
  raw jsonb
);
