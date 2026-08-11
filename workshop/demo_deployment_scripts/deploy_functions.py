"""Register the Unity Catalog functions the agents use as tools.

Everything else in this workshop is retrieval: Genie reads tables, AI Search
finds case notes, the Knowledge Assistant reads documents. A UC function is the
other kind of tool - a calculation the agent is not allowed to do itself.

calculate_sla_credit is the example, and it was chosen because the arithmetic
looks easy and is not. To work out what a customer is owed you have to know
which availability target applies to their plan, that two of the four plans earn
no credits at all, that scheduled maintenance is not downtime, which of the four
tiers the month falls into, and that the whole thing is capped. A model asked to
do this from the SLA document will produce a confident number, and it will
sometimes be the wrong one. Nobody notices, because the output is a plausible
amount of money on a credit note.

So the policy is encoded once, here, in SQL that can be read and audited by the
people who wrote the SLA. The agent supplies a customer and a month and gets
back the number plus the components it was built from, so it can explain the
answer instead of asserting it.

Two deliberate simplifications, recorded here so nobody mistakes them for bugs:

  - The worst-performing service in the month sets the credit. The SLA measures
    per service but caps the total, and stacking per-service credits would breach
    that cap, so taking the worst is both simpler and correct at the boundary.
  - Every service counts, whether or not the customer uses that channel. Saldo
    does not record which channels a customer is entitled to, and inventing that
    mapping would make the function look more precise than its inputs are.

Usage:
    uv run workshop/scripts/deploy_functions.py --dry-run
    uv run workshop/scripts/deploy_functions.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dbx  # noqa: E402

FUNCTION_COMMENT = (
    "Works out the service credit a customer can claim for a given month under the Saldo "
    "Service Level Agreement (SALDO-DOC-0040), and returns the figures the answer was built "
    "from so it can be explained. Call this rather than working a credit out from the SLA "
    "document: the targets differ by plan, Standard and the internal plans earn no credits, "
    "and the tiers are easy to misread. "
    "SCOPE: this covers the service being unavailable, and nothing else. Rejected payroll "
    "records, out-of-date customer data and missed cut-offs are the service working correctly "
    "and earn no credit however disruptive they were - see section 6 of the SLA. If a customer "
    "is asking to be compensated for rejections, this function is not the answer to their "
    "question."
)


def build_sql(cfg: dict) -> str:
    fq = dbx.qualified_function(cfg, "calculate_sla_credit")
    clients = dbx.fq_table(cfg, "clients")
    availability = dbx.fq_table(cfg, "service_availability_daily")

    return f"""
CREATE OR REPLACE FUNCTION {fq}(
  customer_name STRING COMMENT
    "The customer, named the way people say it, for example 'Alpine Retail'. Matched without
     regard to case against clients.short_name, so the legal form ('a.s.', 's.r.o.') can be
     left off.",
  affected_month STRING COMMENT
    "The calendar month being claimed for, as YYYY-MM, for example '2026-07'. The SLA is
     measured monthly, so a single day cannot be claimed on its own."
)
RETURNS TABLE (
  customer STRING COMMENT "The customer this was worked out for.",
  plan STRING COMMENT "Their subscription plan, which sets the target and whether credits apply.",
  affected_month STRING COMMENT "The month claimed for.",
  worst_service STRING COMMENT "The service with the lowest availability that month. It sets the credit.",
  measured_availability_pct DECIMAL(8,4) COMMENT "What that service actually achieved, as a percentage. Scheduled maintenance is already excluded.",
  target_availability_pct DECIMAL(8,4) COMMENT "What their plan promises.",
  target_met BOOLEAN COMMENT "True when every service held its target, in which case no credit is due.",
  plan_earns_credits BOOLEAN COMMENT "False on Standard and internal plans, which carry no credit entitlement at all.",
  monthly_fee_czk BIGINT COMMENT "What the customer is billed for the month, in CZK. The credit is a percentage of this.",
  credit_pct INT COMMENT "The percentage due under the SLA credit table. Zero when nothing is due.",
  credit_czk DECIMAL(14,2) COMMENT "The credit itself, in CZK. Issued against a future invoice, never paid in cash.",
  outcome STRING COMMENT "One sentence explaining the result, safe to repeat to the customer."
)
COMMENT {dbx.sql_string(FUNCTION_COMMENT)}
RETURN
  WITH cust AS (
    SELECT
      short_name, plan, monthly_fee,
      CASE plan
        WHEN 'Enterprise'   THEN 99.95
        WHEN 'Professional' THEN 99.90
        WHEN 'Standard'     THEN 99.50
      END AS target,
      plan IN ('Enterprise', 'Professional') AS earns_credits
    FROM {clients}
    WHERE lower(short_name) = lower(trim(calculate_sla_credit.customer_name))
  ),
  worst AS (
    -- uptime_pct already has scheduled maintenance taken out of it, which is
    -- what SLA section 3 requires. Do not subtract it again.
    SELECT service, round(avg(uptime_pct), 4) AS pct
    FROM {availability}
    WHERE date_format(day, 'yyyy-MM') = trim(calculate_sla_credit.affected_month)
    GROUP BY service
    ORDER BY pct ASC
    LIMIT 1
  ),
  scored AS (
    SELECT
      c.short_name, c.plan, c.monthly_fee, c.target, c.earns_credits,
      w.service, w.pct,
      w.pct IS NULL OR w.pct >= c.target AS met,
      CASE
        WHEN NOT c.earns_credits          THEN 0
        WHEN w.pct IS NULL                THEN 0
        WHEN w.pct >= c.target            THEN 0
        WHEN w.pct >= 99.0                THEN 5
        WHEN w.pct >= 98.0                THEN 10
        WHEN w.pct >= 95.0                THEN 15
        ELSE 25
      END AS pct_due
    FROM cust c LEFT JOIN worst w ON true
  )
  SELECT
    short_name,
    plan,
    trim(calculate_sla_credit.affected_month),
    service,
    CAST(pct AS DECIMAL(8,4)),
    CAST(target AS DECIMAL(8,4)),
    met,
    earns_credits,
    monthly_fee,
    pct_due,
    CAST(round(monthly_fee * pct_due / 100.0, 2) AS DECIMAL(14,2)),
    CASE
      WHEN pct IS NULL THEN
        concat('Saldo holds no availability figures for ', trim(calculate_sla_credit.affected_month),
               ', so no claim can be assessed for that month.')
      WHEN NOT earns_credits THEN
        concat(short_name, ' is on the ', plan, ' plan, which does not include service credits. ',
               'Lowest availability in ', trim(calculate_sla_credit.affected_month), ' was ',
               format_number(pct, 3), '% on the ', service, ' service.')
      WHEN met THEN
        concat('Every Saldo service met the ', format_number(target, 2), '% target for ',
               short_name, ' in ', trim(calculate_sla_credit.affected_month),
               '. The lowest was ', service, ' at ', format_number(pct, 3),
               '%. No service credit is due.')
      ELSE
        concat(service, ' availability was ', format_number(pct, 3), '% in ',
               trim(calculate_sla_credit.affected_month), ', below the ',
               format_number(target, 2), '% target on the ', plan, ' plan. ',
               'A credit of ', CAST(pct_due AS STRING), '% of the ',
               format_number(monthly_fee, 0), ' CZK monthly fee applies, which is ',
               format_number(round(monthly_fee * pct_due / 100.0, 2), 2),
               ' CZK against a future invoice.')
    END
  FROM scored
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="print the DDL, create nothing")
    ap.add_argument("--profile", help="Databricks CLI profile")
    args = ap.parse_args()

    cfg = dbx.load_config()
    ddl = build_sql(cfg)

    if args.dry_run:
        print(ddl)
        print("nothing created (--dry-run)")
        return 0

    w = dbx.workspace(cfg, args.profile)
    dbx.ensure_schemas(w, cfg)
    dbx.sql(w, cfg["warehouse_id"], ddl)
    fq = dbx.qualified_function(cfg, "calculate_sla_credit")
    print(f"  created {fq}")

    # Prove it works on the three cases that matter, so a broken deployment is
    # obvious here rather than in front of a room.
    checks = [
        ("Alpine Retail", "2026-07", "incident month - platform held its target"),
        ("Alpine Retail", "2026-05", "genuine breach on the web service"),
        ("Naldex", "2026-05", "same month, Standard plan, no entitlement"),
    ]
    print()
    for customer, month, why in checks:
        r = dbx.sql(w, cfg["warehouse_id"],
                    f"SELECT credit_pct, credit_czk, outcome FROM {fq}"
                    f"({dbx.sql_string(customer)}, {dbx.sql_string(month)})")
        rows = r.result.data_array or []
        if not rows:
            print(f"  {customer} {month}: NO ROW - check clients.short_name")
            continue
        pct, czk, outcome = rows[0]
        print(f"  {customer} {month}  credit {pct}% = {czk} CZK   ({why})")
        print(f"    {outcome}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
