# Subscription Agreement — Tenzo

*[AI Explanation]: The signed contract between Saldo and Tenzo. It covers what Tenzo subscribes to,
what they pay, what Saldo commits to, and how responsibility is divided between the two. Where this
agreement and Saldo's standard published terms differ, this agreement takes precedence.*

**Agreement reference:** SAL-2023-0071
**Between:** Saldo s.r.o., Karlovo náměstí 12, 120 00 Praha 2, Czech Republic ("Saldo", "we")
**And:** Tenzo s.r.o., Kubelíkova 723/8, 460 07 Liberec, Czech Republic ("Tenzo", "you")
**Signed:** 15 June 2023
**In force from:** 1 July 2023 until 30 June 2024
**Current period:** 1 July 2026 to 30 June 2027, renewed under clause 2

---

## 1. Services

Saldo provides Tenzo with access to Saldo on the **Professional** plan, for use in Tenzo's own
business.

Saldo is cloud accounting software. Tenzo's finance team uses it to keep its books, issue and chase
invoices, run payroll, file its returns, and reconcile against its bank accounts. Saldo provides the
system and applies the statutory rules; the work is done by Tenzo.

The subscribed modules are listed in Schedule A. The subscription covers the web application, the
SFTP channel and the API, for entities and employees in the Czech Republic and Slovakia.

The scope of the service, and what falls outside it, is set out in the Service Description
(SALDO-DOC-0001), which forms part of this agreement. Commercial details are set out in
Schedule A.

## 2. Term and Renewal

This agreement runs for **12 months** from the date it comes into force.

It then renews automatically for successive 12-month periods, unless either party gives three
months' written notice before the end of the current period.

## 3. Fees and Payment

Tenzo pays a monthly subscription based on the number of active employees in the account, at the
rate set out in Schedule A. Saldo invoices monthly in arrears, with payment due within 30 days.

Tenzo's headcount rises for the autumn and winter peak. Temporary warehouse staff count as active
employees in the months their contracts run, on the same basis as permanent staff. The minimum
monthly charge applies in every month, including out of season.

Additional services — off-cycle payroll runs, expedited processing, custom reports — are charged
separately at the rates in Schedule A.

Correction runs are not charged. Where a payroll run leaves employees unpaid and those employees
need to be run again within the same pay period, Saldo makes no charge, regardless of how many
correction runs are required.

Saldo may revise its prices once in any 12-month period, giving three months' notice. If Tenzo does
not accept the revised prices, it may terminate this agreement with effect from the date they would
take effect.

## 4. Service Levels

Saldo commits to the availability targets set out in its Service Level Agreement. For the
Professional plan this is **99.9% per calendar month**.

Where Saldo fails to meet that target, Tenzo may claim a service credit against its next invoice.
Credit amounts and the claim process are set out in the Service Level Agreement.

Service credits compensate for the service being unavailable. They do not compensate for the
outcome of an individual payroll run, and they do not compensate for lost sales.

Payments rejected because the submitted data did not meet Saldo's published file specification are
the service operating as designed. Such rejections do not count towards unavailability and do not
give rise to a service credit.

## 5. Support

Tenzo receives support at the Professional level: extended hours, 07:00–19:00 CET on working days,
by email and telephone.

Response targets by severity are set out in Saldo's Support Policy. Saldo assigns severity based on
the facts of each case. Where Tenzo disagrees with an assigned severity, it may refer the matter to
the duty manager.

## 6. Responsibilities

Saldo is responsible for operating the service, maintaining its availability, processing submitted
data in accordance with the published file specification, and transmitting valid payment
instructions to its banking partner within the agreed timescales.

Tenzo is responsible for the accuracy of the data it submits, including employee bank account
details.

Saldo pays what Tenzo instructs it to pay. Saldo validates that submitted data is well formed —
that an account number is a valid IBAN, that an amount is a positive figure — and rejects anything
that is not. Saldo cannot verify that a correctly formatted account belongs to the intended
recipient. Only Tenzo is in a position to know that.

Where an employee is paid late because of an error in their record, correcting that record is
Tenzo's responsibility. Saldo will assist: support can prepare corrected files for Tenzo to review,
and correction runs are not charged.

**Order and payment volumes.** Tenzo's web shop posts orders and card settlements to Saldo through
the API. Saldo processes what is posted and does not reconcile against the payment processor's own
records; that reconciliation is Tenzo's. Saldo makes no commitment about throughput beyond the
published API rate limits, which apply equally in and out of peak season.

## 7. Changes to the Service

Saldo may change the service during the term, provided it does not reduce the functionality Tenzo
subscribes to without agreement.

Where a change requires Tenzo to take action — updating data, altering an integration, or changing
the format of a submitted file — Saldo gives at least **60 days' notice**. Notice is given by email
to Tenzo's nominated technical contact.

Saldo does not deploy changes that require customer action between 1 November and 15 January,
except where a change is required by law or to remedy a security defect. This reflects that Tenzo
takes half its annual revenue in that window.

## 8. Data Protection

Tenzo's data remains its own. Saldo processes it solely to provide the service, and for no other
purpose. Saldo does not sell it and does not use it to train machine learning models.

Saldo acts as processor and Tenzo as controller. The data processing agreement is attached as
Schedule B.

Payroll records are retained for seven years as required by Czech law. All other data is deleted
within 90 days of this agreement ending. Tenzo may export its data at any time, including after
termination.

## 9. Limitation of Liability

Neither party limits its liability for death or personal injury caused by negligence, for fraud, or
for any other liability that cannot be limited by law.

Subject to that, each party's total liability in any 12-month period is limited to the fees paid
under this agreement during that period.

Neither party is liable for loss of profit, loss of business, or reputational harm.

## 10. Termination

Either party may terminate this agreement immediately if the other:

- commits a material breach and fails to remedy it within 30 days of written notice, or
- becomes insolvent.

Tenzo may also terminate if Saldo fails to meet the availability target in three consecutive
calendar months.

On termination, Saldo refunds any subscription paid in respect of a period after the termination
date.

## 11. General

This agreement is governed by Czech law, and the courts of the Czech Republic have exclusive
jurisdiction.

It constitutes the entire agreement between the parties and supersedes any prior representations or
arrangements.

No variation is effective unless made in writing and signed by both parties.

---

**Signed for Saldo s.r.o.**
Tomáš Richter, Commercial Director

**Signed for Tenzo s.r.o.**
Marek Hruška, Managing Director

---

# Schedule A — Commercial Terms

**Subscribed modules**

| Module | Subscribed |
| --- | --- |
| Bookkeeping | yes |
| Invoicing | yes |
| Payroll | yes |
| Banking | yes |
| Tax | yes |

**Subscription**

| | |
| --- | --- |
| Plan | Professional |
| Employees at signature | 19 |
| Rate per active employee per month | **59 CZK** (standard list price 59 CZK) |
| Minimum monthly charge | 11,800 CZK |
| Billing | Monthly in arrears, payment within 30 days |
| Currency | CZK, excluding VAT |
| Price review | Once per 12 months, three months' notice |

At Tenzo's headcount the minimum monthly charge applies rather than the per-employee rate outside
the peak season. What Tenzo buys at the Professional tier is the availability target, the API and
the extended support hours.

**Additional services**

| Item | Charge |
| --- | --- |
| Correction run, same pay period | Not charged |
| Off-cycle payroll run | 2,500 CZK per run |
| Expedited processing, same-day value | 4,000 CZK per run |
| Custom report development | 12,000 CZK per report |

**Discount**

No discount is applied. The rate is standard list price for the Professional plan, agreed on a
12-month term.

**Nominated contacts**

| Role | Name |
| --- | --- |
| Commercial contact (Tenzo) | Marek Hruška, Managing Director |
| Technical contact (Tenzo) | Marek Hruška, Managing Director |
| Payroll contact (Tenzo) | Marek Hruška, Managing Director |
| Account manager (Saldo) | Tomáš Richter |

---

# Schedule B — Data Processing Agreement

Attached separately under reference SAL-2023-0071-DPA.
