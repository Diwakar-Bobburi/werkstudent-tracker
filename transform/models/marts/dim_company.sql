-- One row per hiring company (name as published; no fuzzy merging yet).
select
    company,
    count(*)                                   as n_postings,
    count(*) filter (where is_active)          as n_active,
    min(first_seen)                            as first_seen,
    max(last_seen)                             as last_seen,
    mode(city)                                 as main_city,
    count(distinct city)                       as n_cities,
    list(distinct source order by source)      as sources
from {{ ref('fct_postings') }}
where company is not null
group by 1
