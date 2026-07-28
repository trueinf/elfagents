-- One row per SKU per market: units on hand against units required, plus the
-- replenishment lead time for that market.
select
    sku_id,
    market,
    units_available,
    units_required,
    lead_time_weeks,
    note
from {{ ref('raw_inventory') }}
