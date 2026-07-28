-- One row per past launch: the decision taken and how it turned out.
select
    launch_id,
    sku_name,
    brand,
    markets,
    decision,
    outcome,
    note
from {{ ref('raw_launch_history') }}
