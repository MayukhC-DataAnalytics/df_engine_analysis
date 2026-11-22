-- ============================================================================
-- DASHBOARD QUERIES
--
-- These are plain SQL queries to paste into the Databricks SQL Editor,
-- one at a time, to build the Lakeview dashboard. Each one is a separate
-- "query" in Databricks SQL that you then turn into a chart ("visualization")
-- and pin onto a dashboard. See LEARN_ME_FIRST.md Step 8 for the clicks.
--
-- The first three just read straight from the marts dbt already built --
-- that's the whole point of doing the hard work in dbt: dashboard queries
-- stay this simple.
-- ============================================================================


-- NOTE ON NAMES: this workspace has its own dedicated catalog named
-- df_project (confirm with `SHOW CATALOGS;`), with three schemas inside
-- it -- raw, staging, mart. Every table below that dbt builds (dims,
-- fact, marts) lives in the mart schema, so it's addressed as
-- df_project.mart.<table>. If your catalog is named something other than
-- "df_project", replace it everywhere below.

-- (1) BAR CHART: average efficiency & emissions by combustion mode
-- CAUTION: in this synthetic data the three modes are almost identical
-- (e.g. average score 10.07 / 10.02 / 9.98), so do not read these small
-- differences as real engine behaviour.
-- Chart type: Bar. X = combustion_mode. Y = avg_thermal_efficiency_pct
-- (add avg_nox_emissions / avg_target_score as extra Y series if you like)
-- Chart name: Efficiency & Emissions by Combustion Mode
select *
from df_project.mart.mart_performance_by_mode;


-- (2) LINE/BAR CHART: emissions & efficiency across engine load buckets
-- Chart type: Line. X = engine_load_bucket. Y = avg_nox_emissions,
-- avg_soot_emissions, avg_co_emissions (plot all 3 as separate lines)
-- Chart name: Emissions & Efficiency vs. Engine Load
select *
from df_project.mart.mart_emissions_by_load_bucket;


-- (3) PIE/DONUT CHART: how many readings fall into each performance bucket
-- Chart type: Pie. Angle = number_of_readings. Group = target_category
-- Chart name: Readings by Performance Category
select *
from df_project.mart.mart_target_category_summary;


-- (4) COUNTER / "BIG NUMBER" tiles for the top of the dashboard
-- Chart type: Counter. One counter per column -- run this once, make
-- 4 separate counter tiles pointed at the same query.
-- Chart names: Total Readings | Avg Thermal Efficiency % | Avg NOx Emissions | Avg Target Score
select
    count(*)                                  as total_readings,
    round(avg(thermal_efficiency_pct), 2)     as avg_thermal_efficiency_pct,
    round(avg(nox_emissions_g_per_kwh), 3)    as avg_nox_emissions,
    round(avg(target_score), 2)               as avg_target_score
from df_project.mart.fct_engine_readings;


-- (5) SCATTER PLOT: does the air/fuel mix (equivalence_ratio) track with NOx?
-- A HIGHER equivalence ratio means a RICHER mix. In this synthetic data there
-- is essentially no relationship (correlation about 0.01), so use this as an
-- "expected vs observed" panel: real engines would show a pattern.
-- This is raw exploration straight against the
-- fact table -- a taste of what you can do beyond the pre-built marts.
-- Chart type: Scatter. X = equivalence_ratio. Y = nox_emissions_g_per_kwh.
-- Color/group by combustion_mode to see if the pattern differs per mode.
-- Chart name: Air-Fuel Ratio vs. NOx
select
    equivalence_ratio,
    nox_emissions_g_per_kwh,
    combustion_mode
from df_project.mart.fct_engine_readings f
join df_project.mart.dim_combustion_mode m
  using (combustion_mode_id);


-- (6) TABLE: the 10 best-performing simulated operating conditions
-- Chart type: Table (or leave it as a results grid).
-- Useful as a "what does a great run actually look like" reference panel.
-- Chart name: Top 10 Best-Performing Runs
select
    reading_id,
    engine_load_percent,
    injection_timing_deg,
    equivalence_ratio,
    boost_pressure_bar,
    thermal_efficiency_pct,
    nox_emissions_g_per_kwh,
    target_score
from df_project.mart.fct_engine_readings
order by target_score desc
limit 10;


-- (7) SCATTER PLOT: NOx vs fuel injection pressure -- the one strong
-- relationship in this synthetic data (correlation about 0.99).
-- Chart type: Scatter. X = fuel_injection_pressure_bar. Y = nox_emissions_g_per_kwh.
-- Chart name: Fuel Injection Pressure vs. NOx
select
    fuel_injection_pressure_bar,
    nox_emissions_g_per_kwh,
    combustion_mode
from df_project.mart.fct_engine_readings f
join df_project.mart.dim_combustion_mode m
  using (combustion_mode_id);


-- (8) BAR CHART: same engine, different duty cycle (the new headline chart)
-- Chart type: Bar. X = cycle_name. Y = weighted_bsfc_g_per_kwh
-- (add weighted_thermal_efficiency_pct as another series if you like).
-- ISO8178_E3 and ISO8178_D2 are standard test-cycle weights from published
-- summaries; ILLUSTRATIVE_LIGHT_LOAD_GENSET is made up for demonstration.
-- Chart name: Same Engine, Different Duty Cycle
select *
from df_project.mart.mart_duty_cycle_performance;


-- (9) TABLE/LINE: the engine map at each exact load point
-- Chart type: Line. X = engine_load_percent. Y = avg_bsfc_g_per_kwh.
-- Chart name: Engine Map by Load
select *
from df_project.mart.mart_engine_map_by_load
order by engine_load_percent;


-- ============================================================================
-- (10) BUSINESS TOOL: Fuel Cost & Emissions Compliance Calculator
--
-- WHY THIS QUERY EXISTS
-- Queries 1-9 answer engineering questions ("which combustion mode is more
-- efficient?"). A buyer or a research lab doesn't think in g/kWh -- they
-- think in dollars per year and "do we pass the regulation or not?". This
-- query converts the duty-cycle mart into exactly those two things, so the
-- same pipeline can be pitched as a decision tool, not just a report.
--
-- WHAT MAKES THIS REUSABLE AS A PRODUCT
-- Every number that is specific to ONE customer/engine/fuel market lives in
-- the `assumptions` CTE below -- nowhere else in the query. To run this
-- against a different company's engine or a different dataset, you only
-- ever edit the 4 lines in `assumptions`, or swap them for a parameter/widget
-- if this is wired into a dashboard that supports query parameters. No other
-- SQL needs to change, and nothing here depends on this specific CSV --
-- it only needs mart_duty_cycle_performance to exist with the same columns,
-- which is true for any dataset run through this same dbt project.
--
-- Chart type: Bar (annual_fuel_cost_usd by cycle_name, colored by
-- nox_compliance_status) + a Table tile for the full breakdown.
-- Chart name: Fuel Cost & Compliance by Duty Cycle
-- ============================================================================
with assumptions as (
    select
        1.10    as fuel_price_usd_per_kg,     -- EDIT: delivered fuel price, $ per kg
        4000    as annual_operating_hours,    -- EDIT: hours per year this engine actually runs
        14.4    as nox_limit_g_per_kwh,       -- EDIT: the regulatory/contractual NOx ceiling to check against
        1000    as rated_power_kw             -- EDIT: engine's rated power output, kW
),

cycle_economics as (
    select
        d.cycle_name,
        d.industry,
        d.application,
        d.basis,
        d.weighted_bsfc_g_per_kwh,
        d.weighted_thermal_efficiency_pct,
        d.weighted_nox_emissions,
        a.rated_power_kw,
        a.annual_operating_hours,
        a.fuel_price_usd_per_kg,
        a.nox_limit_g_per_kwh,
        -- annual fuel burned (kg) = BSFC (g/kWh) x power (kW) x hours/year, converted g -> kg
        (d.weighted_bsfc_g_per_kwh * a.rated_power_kw * a.annual_operating_hours) / 1000.0
            as annual_fuel_kg,
        -- annual fuel spend = fuel burned x price per kg
        ((d.weighted_bsfc_g_per_kwh * a.rated_power_kw * a.annual_operating_hours) / 1000.0)
            * a.fuel_price_usd_per_kg
            as annual_fuel_cost_usd,
        case
            when d.weighted_nox_emissions <= a.nox_limit_g_per_kwh then 'PASS'
            else 'FAIL'
        end as nox_compliance_status,
        round(
            ((d.weighted_nox_emissions - a.nox_limit_g_per_kwh) / a.nox_limit_g_per_kwh) * 100, 1
        ) as nox_pct_vs_limit
    from df_project.mart.mart_duty_cycle_performance d
    cross join assumptions a
)

select
    cycle_name,
    industry,
    application,
    basis,
    round(weighted_bsfc_g_per_kwh, 2)              as bsfc_g_per_kwh,
    round(weighted_thermal_efficiency_pct, 2)      as thermal_efficiency_pct,
    round(annual_fuel_kg, 0)                       as annual_fuel_kg,
    round(annual_fuel_cost_usd, 0)                 as annual_fuel_cost_usd,
    -- dollars this duty cycle costs you per year versus the cheapest cycle on this same engine
    round(annual_fuel_cost_usd - min(annual_fuel_cost_usd) over (), 0)
        as extra_annual_cost_vs_best_cycle_usd,
    round(weighted_nox_emissions, 3)               as nox_g_per_kwh,
    nox_compliance_status,
    nox_pct_vs_limit as nox_pct_vs_limit_percent
from cycle_economics
order by annual_fuel_cost_usd;


-- ============================================================================
-- (11) BUSINESS TOOL: Combustion-Mode Switching ROI
--
-- Answers: "if we standardized every engine on the single best-performing
-- combustion mode instead of the current mix, what would we save per year?"
-- Same reusability rule as query 10 -- edit only the `assumptions` CTE.
-- Chart type: Bar. X = combustion_mode. Y = annual_fuel_cost_usd.
-- Chart name: Combustion-Mode Switching ROI
-- ============================================================================
with assumptions as (
    select
        1.10    as fuel_price_usd_per_kg,     -- EDIT: delivered fuel price, $ per kg
        4000    as annual_operating_hours,    -- EDIT: hours per year this engine actually runs
        1000    as rated_power_kw             -- EDIT: engine's rated power output, kW
),

mode_economics as (
    select
        m.combustion_mode,
        m.combustion_mode_description,
        m.avg_bsfc_g_per_kwh,
        m.avg_target_score,
        (m.avg_bsfc_g_per_kwh * a.rated_power_kw * a.annual_operating_hours) / 1000.0
            * a.fuel_price_usd_per_kg
            as annual_fuel_cost_usd
    from df_project.mart.mart_performance_by_mode m
    cross join assumptions a
)

select
    combustion_mode,
    combustion_mode_description,
    avg_bsfc_g_per_kwh,
    avg_target_score,
    round(annual_fuel_cost_usd, 0)                                    as annual_fuel_cost_usd,
    round(annual_fuel_cost_usd - min(annual_fuel_cost_usd) over (), 0) as potential_annual_savings_usd_if_switched
from mode_economics
order by annual_fuel_cost_usd;
