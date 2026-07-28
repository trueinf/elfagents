-- The three seeded scenarios are the demo. If the data stops producing these
-- shapes, the disagreement stops being genuine and starts being narrated —
-- so the expected shape is asserted here rather than trusted.
--
--   LAUNCH-1001  US ready, DE blocked, UK ready   -> the four-way split
--   LAUNCH-1002  US ready                         -> clean go
--   LAUNCH-1003  nothing ready anywhere           -> clear slip
--
-- Returns rows (i.e. fails) when actual readiness diverges from expected.

with expected as (

    select 'LAUNCH-1001' as launch_id, 'US' as market, true  as launch_ready
    union all select 'LAUNCH-1001', 'DE', false
    union all select 'LAUNCH-1001', 'UK', true
    union all select 'LAUNCH-1002', 'US', true
    union all select 'LAUNCH-1003', 'US', false
    union all select 'LAUNCH-1003', 'DE', false
    union all select 'LAUNCH-1003', 'UK', false

)

select
    e.launch_id,
    e.market,
    e.launch_ready as expected_launch_ready,
    a.launch_ready as actual_launch_ready
from expected e
left join {{ ref('launch_market_readiness') }} a
    on a.launch_id = e.launch_id
   and a.market = e.market
where a.launch_ready is distinct from e.launch_ready
