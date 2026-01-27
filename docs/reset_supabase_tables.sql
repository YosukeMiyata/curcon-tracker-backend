-- Reset all Supabase tables by truncating data.
-- Run in Supabase SQL Editor.

begin;

truncate table
  convex_pool_history,
  convex_pool_ohlc_daily,
  convex_pool_remarks_history,
  cvx_crv_stake_history,
  cvx_crv_stake_ohlc_daily,
  cvx_stake_history,
  cvx_stake_ohlc_daily,
  deletion_tracking_logs,
  pool_latest,
  pool_meta,
  simulations_history,
  token_ohlc_daily,
  token_price_history,
  usdjpy_history,
  usdjpy_ohlc_daily,
  vault_meta;

commit;
