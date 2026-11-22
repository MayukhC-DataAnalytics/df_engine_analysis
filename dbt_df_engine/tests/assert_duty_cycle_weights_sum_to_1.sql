-- Fails (returns rows) if any duty cycle's weights do not add up to 1.
select
    cycle_name,
    sum(weight) as total_weight
from {{ ref('duty_cycles') }}
group by cycle_name
having abs(sum(weight) - 1) > 0.001
