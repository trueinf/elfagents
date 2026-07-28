-- One row per ingredient per market. annex_status distinguishes an outright
-- prohibition (annex_ii_prohibited — banned at any concentration) from a
-- conditional restriction (annex_iii_restricted — allowed up to max_limit_pct).
-- That distinction is what makes the Regulatory component an agent rather than
-- a flag lookup: the first is fatal, the second is fixable.
select
    ingredient_id,
    inci_name,
    market,
    annex_status,
    max_limit_pct,
    note
from {{ ref('raw_ingredients') }}
