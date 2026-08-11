# Payroll Run Guide

*[AI Explanation]: How a payroll run works, from uploading a file to money reaching employees. What each status
means, and where to look when a run doesn't do what the customer expected.*

**Document ID:** SALDO-DOC-0008
**Applies to:** Saldo Payroll, all plans
**Version:** 5.4
**Last updated:** 12 May 2026
**Owner:** Product — Payroll Core

---

## 1. What a payroll run is

A payroll run is one batch of employee payments for one pay period. A customer typically
performs one run per month, plus occasional off-cycle runs for corrections, bonuses or
terminations.

Each run has an identifier in the form `PR-YYYYMM-NNNN`, for example `PR-202608-0417`.

## 2. Stages

```
Upload  →  Validation  →  Calculation  →  Approval  →  Submission  →  Disbursement  →  Confirmation
```

| Stage | What happens | Typical duration |
| --- | --- | --- |
| Upload | The payroll input file is received and stored | seconds |
| Validation | Every row is checked against the file specification | under 2 minutes for 5,000 rows |
| Calculation | Statutory deductions are applied and the net amount per employee is produced | under 5 minutes for 5,000 rows |
| Approval | An authorised user reviews the calculated result and releases the run | customer-dependent |
| Submission | Instructions are sent to the banking partner | minutes |
| Disbursement | The partner executes the credits | same day or next value date |
| Confirmation | Per-payment outcomes are returned and reconciled | up to 2 business days |

## 3. Run statuses

| Status | Meaning |
| --- | --- |
| `DRAFT` | Uploaded, not yet validated |
| `VALIDATING` | Validation in progress |
| `VALIDATION_FAILED` | The whole file was rejected — no rows can proceed |
| `CALCULATING` | Deductions are being applied to the rows that passed validation |
| `AWAITING_APPROVAL` | Calculation finished, waiting for an authorised approver |
| `APPROVED` | Released, queued for submission |
| `SUBMITTED` | Sent to the banking partner |
| `COMPLETED` | All payments confirmed |
| `PARTIALLY_COMPLETED` | Some payments confirmed, some rows rejected or failed |
| `FAILED` | Submission failed in full |
| `CANCELLED` | Withdrawn by the customer before submission |

`PARTIALLY_COMPLETED` is a normal outcome, not an error state. It means the run did its job for
every row that was valid.

## 4. Cut-off times

| Channel | Cut-off | Value date |
| --- | --- | --- |
| Web application | 14:00 CET | Next business day |
| SFTP | 12:00 CET | Next business day |
| Payroll API | 14:00 CET | Next business day |

Runs approved after the cut-off are carried to the following business day. Approvals on
weekends and Czech public holidays are processed on the next business day.

## 5. Partial completion and unpaid employees

When a run completes partially, the employees on the rejected rows have **not** been paid.
Saldo does not retry them automatically.

The customer should:

1. Download the rejection report from the run detail screen.
2. Correct the employee records for the affected employees.
3. Submit a correction run containing only the affected employees.

Correction runs within the same pay period are not charged. See *Fee Schedule*
(SALDO-DOC-0031).

## 6. Where to look when a run goes wrong

| Symptom | Look at |
| --- | --- |
| Whole file rejected | The file-level error code — see SALDO-DOC-0021 |
| Some employees unpaid | The rejection report |
| Nothing happened after approval | Run status and cut-off time |
| Payments left the account but did not arrive | Confirmation stage, `PAY-1xx` codes |

## 7. Related documents

- *Payroll Input File — Format Specification* — SALDO-DOC-0012
- *Validation Error Reference* — SALDO-DOC-0021
- *Managing Employee Data* — SALDO-DOC-0015
