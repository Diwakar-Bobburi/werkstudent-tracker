-- Market pulse per source per day: how many listed, how many new, how many taken down.
with days as (
    select distinct source, snapshot_date
    from {{ ref('fct_posting_snapshots') }}
),

days_with_prev as (
    select
        source,
        snapshot_date,
        lag(snapshot_date) over (partition by source order by snapshot_date) as prev_snapshot
    from days
),

active as (
    select source, snapshot_date, count(*) as active_postings
    from {{ ref('fct_posting_snapshots') }}
    group by 1, 2
),

new_postings as (
    select source, first_seen as snapshot_date, count(*) as new_postings
    from {{ ref('fct_postings') }}
    group by 1, 2
),

-- seen on the previous snapshot day but not on this one
removed as (
    select d.source, d.snapshot_date, count(s.posting_key) as removed_postings
    from days_with_prev d
    join {{ ref('fct_posting_snapshots') }} s
        on s.source = d.source and s.snapshot_date = d.prev_snapshot
    left join {{ ref('fct_posting_snapshots') }} today
        on today.posting_key = s.posting_key and today.snapshot_date = d.snapshot_date
    where today.posting_key is null
    group by 1, 2
)

select
    d.source,
    d.snapshot_date,
    coalesce(a.active_postings, 0)   as active_postings,
    coalesce(n.new_postings, 0)      as new_postings,
    coalesce(r.removed_postings, 0)  as removed_postings,
    d.snapshot_date >= cast('{{ var("full_window_since") }}' as date) as is_full_window
from days_with_prev d
left join active a       using (source, snapshot_date)
left join new_postings n using (source, snapshot_date)
left join removed r      using (source, snapshot_date)
order by d.snapshot_date, d.source
