-- One row per SKU: the state of the social trend window and its velocity index.
-- This is what gives the Supply agent a cost of delay to weigh against a gate.
select
    sku_id,
    window_status,
    velocity_index,
    note
from {{ ref('raw_trend_signals') }}
