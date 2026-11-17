{{ config(materialized='incremental', unique_key='usage_key', incremental_strategy='delete+insert') }}

-- Daily usage per account. Late events are handled by re-aggregating the last
-- few days on every run (var usage_lookback_days).
select
    account_id || '|' || event_date as usage_key,
    account_id,
    event_date,
    count(*) as events,
    count(distinct user_hash) as active_users,
    sum(case when event_type = 'report_created' then 1 else 0 end) as reports_created,
    sum(case when event_type = 'api_call' then 1 else 0 end) as api_calls
from {{ ref('stg_events__product_events') }}
{% if is_incremental() %}
-- coalesce: an empty target (first run had no events yet) must not filter everything out
where event_date >= coalesce(
    (select {{ add_days('max(event_date)', -var('usage_lookback_days')) }} from {{ this }}),
    '1900-01-01')
{% endif %}
group by account_id, event_date
