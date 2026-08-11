# Payroll Input File — Format Specification

*[AI Explanation]: The format of the monthly file a customer submits to run payroll. It carries
what changes each month — hours, bonuses, absence — and nothing else. Who the employee is and
where they get paid comes from the employee master.*

**Document ID:** SALDO-DOC-0012
**Applies to:** Saldo Payroll, all plans
**Version:** 6.2
**Last updated:** 2 July 2026
**Owner:** Product — Payroll

---

## 1. Purpose

This document defines the file a customer submits to run payroll for a pay period.

The file carries **only what changes each month**: hours worked, bonuses, absence. Everything
stable about an employee — their name, their contract, their rate, their bank account — lives in
the employee master and is not repeated here.

Files can be submitted through the web application, through SFTP, or through the Payroll API.
The format is identical in all three.

## 2. File-level requirements

| Property | Requirement |
| --- | --- |
| Encoding | UTF-8. A byte-order mark is tolerated and stripped. |
| Delimiter | Semicolon (`;`) |
| Line ending | CRLF or LF |
| Header row | Required. Column names must match section 4 exactly, in any order. |
| Decimal separator | Dot (`.`). Comma is rejected. |
| Maximum rows | 20,000 per file |
| Maximum size | 25 MB |
| File name | Free text. The extension must be `.csv`. |

Files breaching the row or size limit are rejected in full with `VAL-002`.

## 3. Processing model

Validation happens in two passes.

**The file is checked first.** Structure, columns, data types, and whether each `employee_id`
exists in the employee master.

**Then each employee's record is checked.** For every row that survived the first pass, Saldo
validates the master record it points at — that the contract is current, and that the bank
account is valid.

Both passes are **per row, not per file**. A file containing good and bad rows is processed
partially:

- Rows that pass both checks continue to calculation, approval and payment.
- Rows that fail either check are held with status `REJECTED` and are not paid.

This is deliberate. A handful of bad records should not stop everyone else being paid. It does
mean a run can finish as `PARTIALLY_COMPLETED` with some employees unpaid — see *Payroll Run
Guide* (SALDO-DOC-0008), section 5.

Rejected rows can be corrected and resubmitted as a correction run at no charge within the same
pay period. See *Fee Schedule* (SALDO-DOC-0031).

## 4. Column definitions

| Column | Type | Required | Rules |
| --- | --- | --- | --- |
| `employee_id` | string(20) | yes | Must be unique in the file and exist in the employee master. |
| `period` | string(7) | yes | Pay period as `YYYY-MM`. Must match the run's period. |
| `hours_worked` | decimal(7,2) | conditional | Required for hourly contracts. Ignored for salaried contracts. |
| `gross_amount` | decimal(12,2) | conditional | Required for salaried contracts. For hourly contracts, overrides the calculated gross if supplied. |
| `bonus` | decimal(12,2) | no | Added to gross before deductions. |
| `absence_days` | decimal(5,2) | no | Unpaid absence in the period. |
| `cost_centre` | string(20) | no | Must exist in the customer's cost centre list if supplied. |
| `note` | string(35) | no | Free text carried onto the payslip. |

Whether an employee is hourly or salaried comes from their contract in the employee master, not
from the file. Supplying `hours_worked` for a salaried employee is not an error — it is ignored.

## 5. What is *not* in this file

These are supplied by the employee master, and cannot be set or overridden from the file:

- Name and personal number
- Bank account
- Contract type, hourly rate or monthly salary
- Tax residency and allowances

Employee payment details are maintained in the employee master. See *Managing Employee Data*
(SALDO-DOC-0015).

## 6. Worked example

```
employee_id;period;hours_worked;gross_amount;bonus;absence_days;cost_centre;note
E-1042;2026-08;168.00;;2000.00;0;STORE-BRNO-01;
E-1043;2026-08;152.50;;0;1.5;STORE-BRNO-01;
E-2277;2026-08;;68000.00;0;0;HQ;
```

The first two rows are hourly employees; the third is salaried.

## 7. Related documents

- *Payroll Run Guide* — SALDO-DOC-0008
- *Validation Error Reference* — SALDO-DOC-0021
- *Managing Employee Data* — SALDO-DOC-0015
