-- One row per SKU per selling channel (retail account or owned DTC storefront).
--
-- compliance_dossier_status is a RETAILER-side receiving condition, not a
-- regulatory fact: it records whether that account has accepted our compliance
-- dossier. EU accounts require it before they will take delivery. It lives here
-- so the Retailer agent can reach its own conclusion about which markets can
-- receive stock without reading regulatory data it does not own.
select
    sku_id,
    retailer,
    market,
    channel,
    status,
    compliance_dossier_status,
    note
from {{ ref('raw_item_setup') }}
