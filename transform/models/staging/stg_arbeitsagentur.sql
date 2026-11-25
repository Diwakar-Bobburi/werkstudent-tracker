-- One row per (posting, fetch). Bundesagentur für Arbeit, v6 field names.
with raw as (
    select * from {{ read_raw('arbeitsagentur') }}
)

select
    'arbeitsagentur'                                                    as source,
    coalesce(payload->>'_id', payload->>'referenznummer', payload->>'refnr') as source_id,
    run_id,
    fetched_at,
    cast(fetched_at as date)                                            as snapshot_date,

    coalesce(payload->>'stellenangebotsTitel', payload->>'titel')       as title,
    coalesce(payload->>'firma', payload->>'arbeitgeber')                as company,
    {{ clean_city("payload->'stellenlokationen'->0->'adresse'->>'ort'") }} as city_raw,
    payload->'stellenlokationen'->0->'adresse'->>'region'               as region_raw,
    payload->'stellenlokationen'->0->'adresse'->>'plz'                  as postcode,
    try_cast(payload->'stellenlokationen'->0->>'breite' as double)      as lat,
    try_cast(payload->'stellenlokationen'->0->>'laenge' as double)      as lon,
    false                                                               as is_remote,

    payload->>'hauptberuf'                                              as occupation,
    try_cast(payload->>'datumErsteVeroeffentlichung' as date)           as published_on,
    try_cast(payload->>'gehaltsspanneVon' as double)                    as salary_min,
    try_cast(payload->>'gehaltsspanneBis' as double)                    as salary_max,
    payload->>'verguetungsangabe'                                       as salary_unit,
    coalesce(
        payload->>'externeUrl',
        'https://www.arbeitsagentur.de/jobsuche/jobdetail/' || coalesce(payload->>'_id', payload->>'referenznummer')
    )                                                                   as url,
    payload->>'_query'                                                  as search_query
from raw
