-- ============================================================================
-- STAGING MODEL: stg_engine_readings
--
-- The job of a staging model is boring on purpose: clean up names, fix
-- types, add an id -- and change NOTHING about the actual meaning of the
-- data. Every other model downstream (dims, facts, marts) will build on
-- top of THIS model, never on the raw table directly. That way, if the
-- raw column names ever change, you only have to fix this one file.
--
-- This file becomes a VIEW in Databricks (see dbt_project.yml), in the
-- catalog/schema: workspace.df_project
-- ============================================================================

with source as (

    -- The source() function is how a model points at a raw table declared
    -- in _sources.yml. dbt turns this into the full catalog.schema.table name.
    select * from {{ source('raw_engine_data', 'dual_fuel_engine_dataset_categorical') }}

),

renamed as (

    select
        -- The raw data has no unique id column, so we make one ourselves.
        -- row_number() just counts 1, 2, 3, ... down the rows.
        row_number() over (order by (select null)) as reading_id,

        Engine_Load_Percent                as engine_load_percent,
        Diesel_Energy_Share                as diesel_energy_share_pct,
        Gasoline_Energy_Share              as gasoline_energy_share_pct,
        Injection_Timing                   as injection_timing_deg,
        Fuel_Injection_Pressure            as fuel_injection_pressure_bar,
        EGR_Rate                           as egr_rate_pct,
        Boost_Pressure                     as boost_pressure_bar,
        Intake_Temperature                 as intake_temperature_k,
        Equivalence_Ratio                  as equivalence_ratio,
        Cylinder_Pressure_Peak             as cylinder_pressure_peak_bar,
        Combustion_Duration                as combustion_duration_deg,
        Combustion_Mode                    as combustion_mode,
        BSFC                               as bsfc_g_per_kwh,
        NOx_Emissions                      as nox_emissions_g_per_kwh,
        Soot_Emissions                     as soot_emissions_g_per_kwh,
        CO_Emissions                        as co_emissions_g_per_kwh,
        Gross_Indicated_Thermal_Efficiency as thermal_efficiency_pct,
        Combustion_Stability_Index         as combustion_stability_index,
        Target_Score                       as target_score,
        Target_Category                    as target_category

    from source

)

select * from renamed
