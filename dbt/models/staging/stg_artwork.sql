-- One row per SKU per market: the state of packaging artwork for that market.
select
    sku_id,
    market,
    status,
    note
from {{ ref('raw_artwork') }}
