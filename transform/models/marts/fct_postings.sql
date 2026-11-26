-- One row per posting: latest attributes + lifecycle.
with latest_attrs as (
    select *
    from {{ ref('stg_postings') }}
    qualify row_number() over (partition by posting_key order by snapshot_date desc) = 1
),

presence as (
    select
        posting_key,
        min(snapshot_date)  as first_seen,
        max(snapshot_date)  as last_seen,
        count(*)            as days_observed
    from {{ ref('fct_posting_snapshots') }}
    group by 1
),

latest_run_per_source as (
    select source, max(snapshot_date) as latest_snapshot
    from {{ ref('fct_posting_snapshots') }}
    group by 1
)

select
    a.posting_key,
    a.source,
    a.source_id,
    a.title,
    a.company,
    a.city,
    a.region,
    a.lat,
    a.lon,
    a.is_remote,
    a.occupation,
    a.published_on,
    a.salary_min,
    a.salary_max,
    a.salary_unit,
    a.salary_period,
    a.salary_period is not null
        and a.salary_period <> case a.salary_unit
            when 'STUNDENLOHN' then 'hourly' when 'MONATSGEHALT' then 'monthly' when 'JAHRESGEHALT' then 'yearly'
            else a.salary_period end                                      as salary_unit_mislabelled,
    a.url,

    p.first_seen,
    p.last_seen,
    p.days_observed,
    p.last_seen = r.latest_snapshot                                        as is_active,
    -- Only trust "it disappeared, so it was taken down" once we fetched the full open list daily.
    (p.last_seen <> r.latest_snapshot
        and p.last_seen >= cast('{{ var("full_window_since") }}' as date))  as is_closed_reliably,
    date_diff('day', coalesce(a.published_on, p.first_seen), p.last_seen)  as days_listed,
    d.posting_key is not null                                              as has_description
from latest_attrs a
join presence p using (posting_key)
join latest_run_per_source r on r.source = a.source
left join {{ ref('stg_descriptions') }} d using (posting_key)
