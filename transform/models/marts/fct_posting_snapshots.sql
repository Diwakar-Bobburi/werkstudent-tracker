-- Slim daily presence table: "posting X was listed on day D". The basis for all lifecycle metrics.
select
    posting_key,
    source,
    snapshot_date
from {{ ref('stg_postings') }}
