-- ============================================================================
-- MART: mart_target_category_summary
--
-- Question: "what do the 'Excellent' runs look like compared to the
-- 'Low' ones?" Good for a quick health-check table or pie chart showing
-- how many runs fall into each performance bucket.
--
-- Dashboard idea: pie/donut chart of number_of_readings by target_category,
-- plus a table showing the other columns.
-- ============================================================================

select
    c.target_category,
    c.min_target_score_seen,
    c.max_target_score_seen,
    count(*)                                              as number_of_readings,
    round(avg(f.thermal_efficiency_pct), 2)                as avg_thermal_efficiency_pct,
    round(avg(f.combustion_stability_index), 3)            as avg_combustion_stability_index
from {{ ref('fct_engine_readings') }} f
join {{ ref('dim_target_category') }} c using (target_category_id)
group by c.target_category, c.min_target_score_seen, c.max_target_score_seen
order by c.min_target_score_seen
