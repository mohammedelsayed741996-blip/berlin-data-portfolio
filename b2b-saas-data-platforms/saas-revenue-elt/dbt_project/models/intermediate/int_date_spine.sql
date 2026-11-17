-- One row per day from the opening-balance date to the run date.
with recursive spine(date_day) as (
    select '{{ var("start_date") }}'
    union all
    select {{ add_days('date_day', 1) }}
    from spine
    where date_day < '{{ var("run_date") }}'
)

select date_day from spine
