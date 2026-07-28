-- =============================================================================
-- GOVERNED DEFINITION: launch_ready
-- Grain: one row per launch per target market.
-- Owner: Director of Commercialization (Stage-Gate / PMO)
-- Version: var('launch_ready_version')
--
-- A market is launch_ready when ALL FOUR of these hold:
--   1. ingredient_compliant   — no prohibited substance, no exceeded limit
--   2. notification_clear     — pre-market notification complete or not required
--   3. item_setup_complete    — every selling channel in that market is set up
--   4. artwork_approved       — packaging artwork approved for that market
--
-- This definition is deliberately NARROWER than what the agents reason over.
-- retailer_dossier_clear and the labelling detail are published here as
-- evidence columns but are NOT part of launch_ready — a specialist may judge a
-- market unready for a reason the governed metric does not encode, and the
-- reconciliation is expected to explain that gap rather than hide it.
--
-- Null handling is fail-CLOSED on every gate we own the record for
-- (notification, item setup, artwork): an absent row means "unproven", not
-- "fine". It is fail-OPEN on ingredients only, where the absence of a
-- restriction row genuinely means no restriction is on record. Tools in the
-- use-case layer surface 'no_record' explicitly rather than returning null, so
-- an agent is never left to infer meaning from silence.
-- =============================================================================

with exploded as (

    select
        launch_id,
        sku_id,
        first_ship_date,
        countdown_weeks,
        scenario,
        trim(unnest(string_split(target_markets, ';'))) as market
    from {{ ref('stg_launches') }}

),

ingredient_gate as (

    select
        si.sku_id,
        i.market,
        bool_and(
            case
                when i.annex_status = 'annex_ii_prohibited' then false
                when i.max_limit_pct is not null
                     and si.concentration_pct > i.max_limit_pct then false
                else true
            end
        ) as ingredient_compliant,
        count(*) filter (
            where i.annex_status = 'annex_ii_prohibited'
        ) as prohibited_ingredient_count,
        count(*) filter (
            where i.annex_status = 'annex_iii_restricted'
              and si.concentration_pct > i.max_limit_pct
        ) as exceeded_restriction_count
    from {{ ref('stg_sku_ingredients') }} si
    inner join {{ ref('stg_ingredients') }} i
        on i.inci_name = si.inci_name
    group by 1, 2

),

notification_gate as (

    select
        sku_id,
        market,
        portal,
        status,
        status in ('complete', 'not_required') as notification_clear
    from {{ ref('stg_notifications') }}

),

item_setup_gate as (

    select
        sku_id,
        market,
        count(*) as channel_count,
        bool_and(status = 'complete') as item_setup_complete,
        bool_and(
            compliance_dossier_status in ('accepted', 'not_required')
        ) as retailer_dossier_clear
    from {{ ref('stg_item_setup') }}
    group by 1, 2

),

artwork_gate as (

    select
        sku_id,
        market,
        status,
        status = 'approved' as artwork_approved
    from {{ ref('stg_artwork') }}

),

labelling_gate as (

    select
        sku_id,
        market,
        count(*) as requirement_count,
        count(*) filter (where status <> 'met') as unmet_requirement_count
    from {{ ref('stg_labelling_requirements') }}
    group by 1, 2

)

select
    e.launch_id,
    e.sku_id,
    s.sku_name,
    s.brand,
    e.market,
    e.first_ship_date,
    e.countdown_weeks,
    e.scenario,

    -- gate 1: ingredients
    coalesce(ig.ingredient_compliant, true) as ingredient_compliant,
    coalesce(ig.prohibited_ingredient_count, 0) as prohibited_ingredient_count,
    coalesce(ig.exceeded_restriction_count, 0) as exceeded_restriction_count,

    -- gate 2: pre-market notification
    coalesce(ng.notification_clear, false) as notification_clear,
    coalesce(ng.portal, 'no_record') as notification_portal,
    coalesce(ng.status, 'no_record') as notification_status,

    -- gate 3: commercial item setup
    coalesce(isg.item_setup_complete, false) as item_setup_complete,
    coalesce(isg.channel_count, 0) as channel_count,

    -- gate 4: packaging artwork
    coalesce(ag.artwork_approved, false) as artwork_approved,
    coalesce(ag.status, 'no_record') as artwork_status,

    -- evidence published alongside the metric, deliberately NOT part of it
    coalesce(isg.retailer_dossier_clear, false) as retailer_dossier_clear,
    coalesce(lg.unmet_requirement_count, 0) as unmet_labelling_requirements,

    -- THE GOVERNED METRIC
    coalesce(ig.ingredient_compliant, true)
        and coalesce(ng.notification_clear, false)
        and coalesce(isg.item_setup_complete, false)
        and coalesce(ag.artwork_approved, false) as launch_ready,

    '{{ var("launch_ready_version") }}' as semantic_version

from exploded e
left join {{ ref('stg_skus') }} s
    on s.sku_id = e.sku_id
left join ingredient_gate ig
    on ig.sku_id = e.sku_id and ig.market = e.market
left join notification_gate ng
    on ng.sku_id = e.sku_id and ng.market = e.market
left join item_setup_gate isg
    on isg.sku_id = e.sku_id and isg.market = e.market
left join artwork_gate ag
    on ag.sku_id = e.sku_id and ag.market = e.market
left join labelling_gate lg
    on lg.sku_id = e.sku_id and lg.market = e.market
