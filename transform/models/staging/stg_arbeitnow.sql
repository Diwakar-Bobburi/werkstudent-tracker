-- One row per (posting, fetch). Arbeitnow job-board API.
with raw as (
    select * from {{ read_raw('arbeitnow') }}
)

select
    'arbeitnow'                                                         as source,
    payload->>'slug'                                                    as source_id,
    run_id,
    fetched_at,
    cast(fetched_at as date)                                            as snapshot_date,

    payload->>'title'                                                   as title,
    payload->>'company_name'                                            as company,
    {{ clean_city("payload->>'location'") }}                            as city_raw,
    cast(null as varchar)                                               as region_raw,
    cast(null as varchar)                                               as postcode,
    cast(null as double)                                                as lat,
    cast(null as double)                                                as lon,
    coalesce(try_cast(payload->>'remote' as boolean), false)            as is_remote,

    cast(null as varchar)                                               as occupation,
    cast(to_timestamp(try_cast(payload->>'created_at' as bigint)) as date) as published_on,
    cast(null as double)                                                as salary_min,
    cast(null as double)                                                as salary_max,
    cast(null as varchar)                                               as salary_unit,
    payload->>'url'                                                     as url,
    payload->>'_query'                                                  as search_query
from raw
