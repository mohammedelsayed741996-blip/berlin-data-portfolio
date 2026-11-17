-- End-of-day MRR per subscription. A version counts on day D if it was written
-- on or before D and replaced after D.
select
    d.date_day || '|' || v.subscription_id as mrr_key,
    d.date_day,
    v.account_id,
    v.subscription_id,
    v.plan,
    v.seats,
    v.mrr_eur
from {{ ref('int_date_spine') }} d
join {{ ref('int_subscription_versions') }} v
    on v.valid_from_date <= d.date_day
   and (v.valid_to_date is null or v.valid_to_date > d.date_day)
where v.mrr_eur > 0
