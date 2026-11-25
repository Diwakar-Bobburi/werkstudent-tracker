-- Werkstudent hourly pay outside 10-60 EUR is almost certainly a data error worth a look.
{{ config(severity = 'warn') }}
select posting_key, salary_min, salary_max
from {{ ref('fct_postings') }}
where salary_period = 'hourly'
  and (salary_min < 10 or salary_max > 60)
