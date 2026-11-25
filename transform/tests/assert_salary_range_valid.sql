-- Published ranges must be positive and ordered.
select posting_key, salary_min, salary_max
from {{ ref('fct_postings') }}
where salary_min < 0
   or salary_max < 0
   or (salary_min is not null and salary_max is not null and salary_min > salary_max)
