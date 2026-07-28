-- One row per launch record in the launch calendar.
select
    launch_id,
    sku_id,
    target_markets,
    first_ship_date,
    countdown_weeks,
    scenario
from {{ ref('raw_launches') }}
