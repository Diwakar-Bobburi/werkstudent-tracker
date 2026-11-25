-- Both sources in one shape, cities normalised, one row per posting per snapshot day.
with unioned as (
    select * from {{ ref('stg_arbeitsagentur') }}
    union all by name
    select * from {{ ref('stg_arbeitnow') }}
),

with_city as (
    select
        u.*,
        coalesce(a.city, u.city_raw)    as city,
        coalesce(st.state, u.region_raw) as region
    from unioned u
    left join {{ ref('city_aliases') }} a
        on lower(u.city_raw) = a.raw_city
    -- "NORDRHEIN-WESTFALEN" / "Baden_Wuerttemberg" -> one key -> proper German name
    left join {{ ref('german_states') }} st
        on regexp_replace(lower(u.region_raw), '[^a-zäöüß]', '', 'g') = st.state_key
)

select
    source || ':' || source_id as posting_key,
    * exclude (city_raw, region_raw),
    -- Employers often pick the wrong pay unit (e.g. "Stundenlohn" with 800-1600 = monthly).
    -- Infer the real period from the amount; keep the stated unit for comparison.
    case
        when coalesce(salary_max, salary_min) is null then null
        when coalesce(salary_max, salary_min) < 100   then 'hourly'
        when coalesce(salary_max, salary_min) < 15000 then 'monthly'
        else 'yearly'
    end as salary_period
from with_city
where source_id is not null
-- Several runs on one day (manual + scheduled) -> keep the latest
qualify row_number() over (partition by source, source_id, snapshot_date order by fetched_at desc) = 1
