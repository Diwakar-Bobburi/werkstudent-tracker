-- Warn if a source has had no successful snapshot for 3+ days (the daily job is silently broken).
{{ config(severity = 'warn') }}
select source, max(snapshot_date) as latest
from {{ ref('fct_posting_snapshots') }}
group by 1
having max(snapshot_date) < current_date - interval 3 day
