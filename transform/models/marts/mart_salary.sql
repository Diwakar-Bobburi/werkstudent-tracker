-- Published pay ranges (Arbeitsagentur only; Arbeitnow has no salary field).
-- Grouped by the INFERRED pay period: hourly, monthly and yearly figures are never mixed.
with paid as (
    select coalesce(city, 'Unknown') as city, salary_period, salary_min, salary_max, salary_unit_mislabelled
    from {{ ref('fct_postings') }}
    where salary_period is not null
)

select
    case when grouping(city) = 1 then '(all of Germany)' else city end as city,
    salary_period,
    count(*)                                        as n_postings,
    count(*) filter (where salary_unit_mislabelled) as n_unit_mislabelled,
    round(median(salary_min), 2)                    as median_min,
    round(median(salary_max), 2)                    as median_max,
    round(min(salary_min), 2)                       as lowest_min,
    round(max(salary_max), 2)                       as highest_max
from paid
group by grouping sets ((city, salary_period), (salary_period))
order by salary_period, grouping(city) desc, n_postings desc
