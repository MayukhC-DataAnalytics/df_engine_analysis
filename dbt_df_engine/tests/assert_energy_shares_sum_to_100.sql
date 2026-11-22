-- Fails (returns rows) if diesel share + gasoline share is not 100 percent.
select
    reading_id,
    diesel_energy_share_pct,
    gasoline_energy_share_pct
from {{ ref('stg_engine_readings') }}
where abs(diesel_energy_share_pct + gasoline_energy_share_pct - 100) > 0.01
