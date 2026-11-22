-- ============================================================================
-- MART: mart_duty_cycle_performance
--
-- "Same engine, different life." Takes the engine map (average results at
-- each load point) and weights it by each duty cycle in the duty_cycles seed:
--     weighted result = sum(weight x result at that load) / sum(weight)
-- so every industry's way of using the engine gives its own fuel and
-- emissions figure.
--
-- The data is synthetic, so treat the numbers as a demonstration of the
-- method, not as real engine results.
-- ============================================================================

with weighted as (

    select
        c.cycle_name,
        c.industry,
        c.application,
        c.basis,
        count(*)                                                               as load_points_used,
        sum(c.weight)                                                          as total_weight,
        sum(c.weight * m.avg_bsfc_g_per_kwh)        / sum(c.weight)            as weighted_bsfc_g_per_kwh,
        sum(c.weight * m.avg_thermal_efficiency_pct) / sum(c.weight)           as weighted_thermal_efficiency_pct,
        sum(c.weight * m.avg_nox_emissions)         / sum(c.weight)            as weighted_nox_emissions,
        sum(c.weight * m.avg_soot_emissions)        / sum(c.weight)            as weighted_soot_emissions,
        sum(c.weight * m.avg_co_emissions)          / sum(c.weight)            as weighted_co_emissions
    from {{ ref('duty_cycles') }} c
    join {{ ref('mart_engine_map_by_load') }} m
      on c.load_percent = m.engine_load_percent
    group by c.cycle_name, c.industry, c.application, c.basis

)

select
    cycle_name,
    industry,
    application,
    basis,
    load_points_used,
    round(total_weight, 3)                                   as total_weight,
    round(weighted_bsfc_g_per_kwh, 2)                        as weighted_bsfc_g_per_kwh,
    round(weighted_thermal_efficiency_pct, 2)                as weighted_thermal_efficiency_pct,
    round(weighted_nox_emissions, 3)                         as weighted_nox_emissions,
    round(weighted_soot_emissions, 3)                        as weighted_soot_emissions,
    round(weighted_co_emissions, 3)                          as weighted_co_emissions,
    round(weighted_bsfc_g_per_kwh
          - min(weighted_bsfc_g_per_kwh) over (), 2)         as extra_bsfc_vs_best_cycle
from weighted
order by weighted_bsfc_g_per_kwh
