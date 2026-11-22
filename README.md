# Dual-fuel engine analysis (dbt + Databricks)

Same engine, different lives: this project weights a dual-fuel engine map by
duty cycle (how the engine is actually loaded) to compare fuel use,
efficiency and emissions.

## Read this first: the data is synthetic
- The source CSVs are generated, not measured on a real engine.
- Only two relationships behave like physics: NOx rises with fuel injection
  pressure, and efficiency/BSFC improve with load. Soot, CO, stability, peak
  pressure and combustion duration are essentially noise.
- Combustion mode, EGR, boost, timing and intake temperature have no visible effect.
- The source gives no units. Unit suffixes in the column names (g/kWh, bar, K,
  deg) are assumptions.
- So this project demonstrates a METHOD. Do not quote the numbers as engine facts.

## Duty cycles (seeds/duty_cycles.csv)
- ISO8178_E3: propeller-law marine engine, loads 100/75/50/25 % at weights 0.20/0.50/0.15/0.15.
- ISO8178_D2: constant-speed genset / marine auxiliary, loads 100/75/50/25/10 % at 0.05/0.25/0.30/0.30/0.10.
- ILLUSTRATIVE_LIGHT_LOAD_GENSET: made up for demonstration, not a standard.
Weights are taken from published summaries of ISO 8178-4, not the standard itself. Check them before publishing.

Weighted value = sum(weight x value at that load) / sum(weight).

## Models
- staging: stg_engine_readings (view)
- marts: fct_engine_readings, dims, mart_engine_map_by_load (one row per exact load),
  mart_duty_cycle_performance (the headline model), mart_emissions_by_load_bucket
- seeds: duty_cycles
- tests: generic tests in the yml files, plus two singular tests (energy shares sum to 100; cycle weights sum to 1)

## Run (Windows, in the folder containing dbt_project.yml)
    dbt debug
    dbt seed
    dbt build

Then in the Databricks SQL editor:
    select * from workspace.df_project.mart_duty_cycle_performance;

Expected weighted BSFC: E3 236.21, D2 240.55, light-load genset 245.40.
