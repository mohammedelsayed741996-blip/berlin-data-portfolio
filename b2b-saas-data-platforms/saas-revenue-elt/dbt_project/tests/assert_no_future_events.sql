select event_id, event_date
from {{ ref('stg_events__product_events') }}
where event_date > '{{ var("run_date") }}'
