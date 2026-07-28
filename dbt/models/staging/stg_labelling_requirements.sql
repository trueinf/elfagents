-- One row per SKU per market per labelling requirement. Multiple requirements
-- can apply to one market, which is what lets the Packaging agent judge which
-- gap actually drives the timeline rather than treating artwork as one flag.
select
    sku_id,
    market,
    requirement,
    status,
    note
from {{ ref('raw_labelling_requirements') }}
