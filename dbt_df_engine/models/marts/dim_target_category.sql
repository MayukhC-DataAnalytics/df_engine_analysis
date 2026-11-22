-- ============================================================================
-- DIMENSION TABLE: dim_target_category
--
-- Same idea as dim_combustion_mode: one row per Target_Category label,
-- but here we compute the score range for each label FROM the data itself
-- (instead of hardcoding guesses), using an aggregate query. This is a
-- nice first taste of GROUP BY + aggregate functions in dbt.
-- ============================================================================

select
    row_number() over (order by min(target_score)) as target_category_id,
    target_category,
    min(target_score)          as min_target_score_seen,
    max(target_score)          as max_target_score_seen,
    round(avg(target_score), 2) as avg_target_score_seen
from {{ ref('stg_engine_readings') }}
group by target_category
