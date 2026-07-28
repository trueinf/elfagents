-- One row per SKU.
select
    sku_id,
    sku_name,
    brand,
    category
from {{ ref('raw_skus') }}
