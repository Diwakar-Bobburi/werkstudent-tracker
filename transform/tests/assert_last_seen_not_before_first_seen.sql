select posting_key, first_seen, last_seen
from {{ ref('fct_postings') }}
where last_seen < first_seen
