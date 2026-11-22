{#
    WHAT IS A MACRO?
    A macro is a reusable chunk of Jinja/SQL logic -- basically a function
    you can call from your models. dbt itself calls a macro named
    "generate_schema_name" every time it decides which schema a model
    should land in.

    WHY THIS VERSION?
    df_project is the CATALOG (set in profiles.yml), not a schema prefix.
    Inside that catalog we want exactly three schemas: raw, staging, mart
    (as named by +schema in dbt_project.yml), nothing glued on top.
#}

{% macro generate_schema_name(custom_schema_name, node) -%}

    {%- if custom_schema_name is none -%}

        {{ target.schema }}

    {%- else -%}

        {{ custom_schema_name | trim }}

    {%- endif -%}

{%- endmacro %}
