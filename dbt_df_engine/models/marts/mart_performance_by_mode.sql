-- ============================================================================
-- MART: mart_performance_by_mode
--
-- A "mart" is the final, dashboard-ready layer. Marts are purpose-built
-- for a specific question -- here: "how does each combustion strategy
-- perform on average?" Notice the query itself is simple; all the hard
-- cleaning/joining already happened in staging and the fact/dim tables.
-- That's the whole point of layering: by the time you get here, SQL is easy.
--
-- Dashboard idea: bar chart, one bar per combustion_mode, comparing
-- avg_thermal_efficiency_pct or avg_target_score.
-- ============================================================================

select
    m.combustion_mode,
    m.combustion_mode_description,
    count(*)                                        as number_of_readings,
    round(avg(f.thermal_efficiency_pct), 2)          as avg_thermal_efficiency_pct,
    round(avg(f.bsfc_g_per_kwh), 2)                  as avg_bsfc_g_per_kwh,
    round(avg(f.nox_emissions_g_per_kwh), 3)         as avg_nox_emissions,
    round(avg(f.soot_emissions_g_per_kwh), 3)        as avg_soot_emissions,
    round(avg(f.co_emissions_g_per_kwh), 3)          as avg_co_emissions,
    round(avg(f.target_score), 2)                    as avg_target_score
from {{ ref('fct_engine_readings') }} f
join {{ ref('dim_combustion_mode') }} m using (combustion_mode_id)
group by m.combustion_mode, m.combustion_mode_description
order by avg_target_score desc
