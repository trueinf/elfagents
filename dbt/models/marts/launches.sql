-- One row per launch: the queue the deterministic signal reads.
--
-- at_gate_threshold is what the countdown detector (a TOOL, not an agent —
-- BUILD_SPEC §5.5) fires on. No LLM decides that a launch is due for review;
-- a scheduled check compares countdown_weeks against the threshold.

with readiness as (

    select
        launch_id,
        count(*) as market_count,
        count(*) filter (where launch_ready) as markets_ready,
        count(*) filter (where not launch_ready) as markets_blocked,
        string_agg(
            case when launch_ready then market end, ';' order by market
        ) as ready_markets,
        string_agg(
            case when not launch_ready then market end, ';' order by market
        ) as blocked_markets
    from {{ ref('launch_market_readiness') }}
    group by 1

)

select
    l.launch_id,
    l.sku_id,
    s.sku_name,
    s.brand,
    s.category,
    l.target_markets,
    l.first_ship_date,
    l.countdown_weeks,
    l.scenario,

    r.market_count,
    r.markets_ready,
    r.markets_blocked,
    r.ready_markets,
    r.blocked_markets,

    -- the shape of the problem, before any agent has reasoned about it
    case
        when r.markets_ready = r.market_count then 'all_ready'
        when r.markets_ready = 0 then 'none_ready'
        else 'mixed'
    end as readiness_shape,

    l.countdown_weeks <= {{ var('gate_threshold_weeks', 4) }} as at_gate_threshold,

    '{{ var("launch_ready_version") }}' as semantic_version

from {{ ref('stg_launches') }} l
left join {{ ref('stg_skus') }} s
    on s.sku_id = l.sku_id
left join readiness r
    on r.launch_id = l.launch_id
