-- One row per SKU per market: which pre-market notification portal applies and
-- where the filing stands. The EU (CPNP) and Great Britain (SCPN) are separate
-- portals with separate filings — that split is structural, not incidental.
select
    sku_id,
    market,
    portal,
    status,
    note
from {{ ref('raw_notifications') }}
