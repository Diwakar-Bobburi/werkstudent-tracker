{#
  Read one source's raw envelopes straight from the gzipped JSONL files.
  The payload is kept as JSON (not auto-typed) because API schemas drift;
  each staging model pulls out exactly the fields it needs.
#}
{% macro read_raw(source_name) %}
    read_json(
        '{{ var("raw_path") }}/source={{ source_name }}/*/*.jsonl.gz',
        format = 'newline_delimited',
        compression = 'gzip',
        columns = {
            run_id: 'VARCHAR',
            source: 'VARCHAR',
            fetched_at: 'TIMESTAMPTZ',
            payload: 'JSON'
        }
    )
{% endmacro %}


{# Normalise a free-text location to a clean city name (before the alias seed is applied). #}
{% macro clean_city(expr) %}
    nullif(trim(regexp_replace(
        split_part({{ expr }}, ',', 1),          -- "Aachen, Germany" -> "Aachen"
        '\s*\(.*\)\s*$', ''                      -- "Berlin (Mitte)"  -> "Berlin"
    )), '')
{% endmacro %}
