-- ============================================================================
-- MART: mart_emissions_by_load_bucket
--
-- Question: "as engine load goes up, what happens to emissions and
-- efficiency?"
--
-- CHANGED: this used to group load into four ranges, but the data only has
-- five exact load points (10, 25, 50, 75, 100), so 75 and 100 were merged and
-- the range labels were misleading. It now reads the exact-load engine map,
-- one row per load point.
--
-- The column engine_load_bucket (and the other column names) are kept so the
-- existing dashboard dataset keeps working. Labels look like "1. 10%".
-- ============================================================================

with ranked as (

    select
        *,
        dense_rank() over (order by engine_load_percent) as load_rank
    from {{ ref('mart_engine_map_by_load') }}

)

select
    concat(cast(load_rank as string), '. ', cast(engine_load_percent as string), '%') as engine_load_bucket,
    engine_load_percent,
    number_of_readings,
    round(avg_nox_emissions, 3)            as avg_nox_emissions,
    round(avg_soot_emissions, 3)           as avg_soot_emissions,
    round(avg_co_emissions, 3)             as avg_co_emissions,
    round(avg_thermal_efficiency_pct, 2)   as avg_thermal_efficiency_pct,
    round(avg_bsfc_g_per_kwh, 2)           as avg_bsfc_g_per_kwh
from ranked
order by engine_load_percent
