-- ============================================================================
-- DIMENSION TABLE: dim_combustion_mode
--
-- A "dimension" table holds the DESCRIPTIVE side of your data: one row
-- per category, with human-readable attributes about that category.
-- Dimensions answer "what does this label actually mean?" so that charts
-- and reports don't just show cryptic codes.
--
-- This becomes a TABLE in workspace.df_project
-- ============================================================================

with modes as (

    select distinct combustion_mode
    from {{ ref('stg_engine_readings') }}

)

select
    row_number() over (order by combustion_mode) as combustion_mode_id,
    combustion_mode,
    case combustion_mode
        when 'Diffusion' then
            'Classic diesel-style combustion: fuel burns as it mixes with air after injection.'
        when 'Homogeneous' then
            'Fuel and air are well mixed together before ignition (similar to HCCI combustion).'
        when 'RCCI' then
            'Reactivity Controlled Compression Ignition: blends a low-reactivity fuel (gasoline) with a high-reactivity fuel (diesel) for cleaner, more controllable combustion.'
        else
            'Unknown combustion mode'
    end as combustion_mode_description
from modes
