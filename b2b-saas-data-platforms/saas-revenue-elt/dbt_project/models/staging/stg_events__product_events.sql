select
    event_id,
    account_id,
    user_hash,
    event_type,
    event_ts,
    substr(event_ts, 1, 10) as event_date,
    _source_ref as source_file,
    _loaded_at as loaded_at
from {{ source('raw', 'product_events') }}
