-- ============================================================================
-- FACT TABLE: fct_engine_readings
--
-- A "fact" table holds the MEASUREMENTS side of your data: numbers that
-- were recorded/measured, linked to dimensions by ids. This is the classic
-- "star schema" pattern -- a fact table in the middle, dimensions around it.
--
-- This is also your first look at the ref() function being used to join
-- two other dbt models together. ref() is how dbt models always point at
-- each other -- never hardcode another model's table name, always ref() it.
-- That's what lets dbt build its dependency graph (see `dbt docs generate`).
-- ============================================================================

select
    r.reading_id,
    m.combustion_mode_id,
    c.target_category_id,

    r.engine_load_percent,
    r.diesel_energy_share_pct,
    r.gasoline_energy_share_pct,
    r.injection_timing_deg,
    r.fuel_injection_pressure_bar,
    r.egr_rate_pct,
    r.boost_pressure_bar,
    r.intake_temperature_k,
    r.equivalence_ratio,
    r.cylinder_pressure_peak_bar,
    r.combustion_duration_deg,
    r.bsfc_g_per_kwh,
    r.nox_emissions_g_per_kwh,
    r.soot_emissions_g_per_kwh,
    r.co_emissions_g_per_kwh,
    r.thermal_efficiency_pct,
    r.combustion_stability_index,
    r.target_score

from {{ ref('stg_engine_readings') }} r
left join {{ ref('dim_combustion_mode') }} m using (combustion_mode)
left join {{ ref('dim_target_category') }} c using (target_category)
