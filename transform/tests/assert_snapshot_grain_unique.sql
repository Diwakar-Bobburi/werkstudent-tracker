-- A posting must appear at most once per day.
select posting_key, snapshot_date, count(*) as n
from {{ ref('fct_posting_snapshots') }}
group by 1, 2
having count(*) > 1
