-- Full job-description text, one row per posting (latest version we have).
-- Arbeitnow ships it in the listing; Arbeitsagentur needs the separate details fetch.
with arbeitnow as (
    select
        'arbeitnow:' || (payload->>'slug')        as posting_key,
        payload->>'description'                   as description_html,
        fetched_at
    from {{ read_raw('arbeitnow') }}
),

arbeitsagentur as (
    select
        'arbeitsagentur:' || (payload->>'_id')    as posting_key,
        coalesce(
            payload->>'stellenangebotsBeschreibung',
            payload->>'stellenbeschreibung',
            payload->>'beschreibung'
        )                                         as description_html,
        fetched_at
    from {{ read_raw('arbeitsagentur_details') }}
    where payload->>'_status' = 'ok'
),

unioned as (
    select * from arbeitnow
    union all
    select * from arbeitsagentur
)

select
    posting_key,
    -- strip HTML tags and collapse whitespace so text models / keyword rules see plain text
    trim(regexp_replace(regexp_replace(description_html, '<[^>]+>', ' ', 'g'), '\s+', ' ', 'g')) as description,
    fetched_at as description_fetched_at
from unioned
where nullif(trim(description_html), '') is not null
qualify row_number() over (partition by posting_key order by fetched_at desc) = 1
