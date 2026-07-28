-- The centrepiece of the demo is that Germany on LAUNCH-1001 is a CONDITIONAL
-- restriction that has been exceeded — fixable by reformulation — and not an
-- outright prohibition. That is what makes the Regulatory component an agent
-- (it must judge severity and path) rather than a flag lookup.
--
-- LAUNCH-1003 is the contrast: a genuine Annex II prohibition, where no
-- reformulation of concentration helps.
--
-- If these two collapse into the same shape, the "restricted is not banned"
-- moment in the demo has nothing behind it. Fails if either does.

with actual as (

    select
        launch_id,
        market,
        prohibited_ingredient_count,
        exceeded_restriction_count
    from {{ ref('launch_market_readiness') }}
    where (launch_id = 'LAUNCH-1001' and market = 'DE')
       or (launch_id = 'LAUNCH-1003' and market = 'DE')

),

violations as (

    -- LAUNCH-1001 DE: exactly one exceeded restriction, zero prohibitions
    select
        launch_id,
        market,
        'expected a conditional restriction exceedance and no prohibition' as failure
    from actual
    where launch_id = 'LAUNCH-1001'
      and not (exceeded_restriction_count = 1 and prohibited_ingredient_count = 0)

    union all

    -- LAUNCH-1003 DE: at least one outright prohibition
    select
        launch_id,
        market,
        'expected an outright prohibition' as failure
    from actual
    where launch_id = 'LAUNCH-1003'
      and prohibited_ingredient_count = 0

)

select * from violations
