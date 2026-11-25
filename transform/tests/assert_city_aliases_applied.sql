-- No alias spelling (e.g. "Munich") should survive into the marts.
select p.posting_key, p.city
from {{ ref('fct_postings') }} p
join {{ ref('city_aliases') }} a on lower(p.city) = a.raw_city
