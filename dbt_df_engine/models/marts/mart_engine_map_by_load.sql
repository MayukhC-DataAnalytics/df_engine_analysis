-- ============================================================================
-- MART: mart_engine_map_by_load
--
-- The "engine map": average performance at each EXACT load point
-- (10, 25, 50, 75 and 100 percent). The earlier bucket model merged the 75
-- and 100 percent points together; this one keeps every load point separate,
-- which is what duty-cycle weighting needs.
--
-- Averages are left unrounded on purpose so later maths stays accurate.
-- Downstream models do the rounding.
-- ============================================================================

select
    engine_load_percent,
    count(*)                              as number_of_readings,
    avg(bsfc_g_per_kwh)                   as avg_bsfc_g_per_kwh,
    avg(thermal_efficiency_pct)           as avg_thermal_efficiency_pct,
    avg(nox_emissions_g_per_kwh)          as avg_nox_emissions,
    avg(soot_emissions_g_per_kwh)         as avg_soot_emissions,
    avg(co_emissions_g_per_kwh)           as avg_co_emissions,
    avg(target_score)                     as avg_target_score
from {{ ref('fct_engine_readings') }}
group by engine_load_percent
