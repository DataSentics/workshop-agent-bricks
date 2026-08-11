# Managing Employee Data

*[AI Explanation]: How customers keep their employee records correct in Saldo — including how to update bank
account details in bulk.*

**Document ID:** SALDO-DOC-0015
**Applies to:** Saldo Payroll, all plans
**Version:** 4.1
**Last updated:** 20 June 2026
**Owner:** Product — Core Data

---

## 1. The employee master

Every customer has an employee master: the authoritative record of each employee's identity,
contract and payment details. Payroll files are validated **against** the master — the file
supplies amounts, the master supplies who the person is and where the money goes.

A payroll input file cannot introduce a new employee. Unknown IDs are rejected with `VAL-011`.

## 2. Fields maintained in the master

| Field | Notes |
| --- | --- |
| `employee_id` | Customer's own identifier. Immutable once created. |
| Name, personal number | Used for statutory reporting |
| `bank_account` | Must be a valid IBAN |
| Contract type, start and end dates | Drives eligibility for a run |
| Cost centre | Optional |

## 3. Updating a single employee

**Employees → search → Payment details → Edit.** Changes take effect on the next validation.
Changes made while a run is in `AWAITING_APPROVAL` do not apply to that run; the file must be
re-uploaded.

## 4. Bulk updating bank accounts

Use this when many employees need correcting at once.

1. Go to **Employees → Export → Payment details**. This produces a CSV of every active
   employee with their current `bank_account` value.
2. Complete or correct the `bank_account` column. Values must be valid IBANs; see
   SALDO-DOC-0012 section 5.
3. Go to **Employees → Import → Payment details** and upload the corrected file.
4. The import runs in preview mode first and reports how many records would change and how
   many would fail. Nothing is written until you confirm.
5. Confirm the import.

The import is idempotent. Rows whose value is unchanged are skipped.

## 5. Related documents

- *Payroll Input File — Format Specification* — SALDO-DOC-0012
- *Validation Error Reference* — SALDO-DOC-0021
- *Payroll Run Guide* — SALDO-DOC-0008
