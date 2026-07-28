-- One row per SKU per ingredient, with the concentration in the current formula.
select
    sku_id,
    inci_name,
    concentration_pct
from {{ ref('raw_sku_ingredients') }}
