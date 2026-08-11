# Validation Error Reference

*[AI Explanation]: Every rejected payment carries one of these codes. Look it up here to find out what went wrong
and what to do about it.*

**Document ID:** SALDO-DOC-0021
**Applies to:** Saldo Payroll, all plans
**Version:** 6.2
**Last updated:** 2 July 2026
**Owner:** Product — Payroll Core

---

Every rejected row carries exactly one error code. Codes are stable; the
message text may be reworded.

Codes are shown in the run detail screen, in the downloadable rejection report, and in the
`errorCode` field of the Payroll API.

## File-level errors

These reject the entire file. No rows are processed.

| Code | Message | Cause | Resolution |
| --- | --- | --- | --- |
| `VAL-001` | Unreadable file | Not valid UTF-8, or not a CSV | Re-export the file as UTF-8 CSV |
| `VAL-002` | File too large | Over 20,000 rows or 25 MB | Split the file across multiple runs |
| `VAL-003` | Missing required column | A column from the specification is absent | Add the column and re-upload |
| `VAL-004` | Unknown column | A column not in the specification is present | Remove the column |
| `VAL-005` | Empty file | Header only, or no rows | Check the export |

## Row errors — a problem in the submitted file

These reject the individual row. Remaining rows continue to be processed. **Fix the file and
resubmit.**

| Code | Message | Cause | Resolution |
| --- | --- | --- | --- |
| `VAL-010` | Missing required value | A required column is empty | Populate the value |
| `VAL-011` | Unknown employee | `employee_id` not found in the employee master | Add the employee, or correct the ID |
| `VAL-012` | Duplicate employee in file | The same `employee_id` appears more than once | Remove the duplicate row |
| `VAL-013` | Period mismatch | `period` does not match the run's pay period | Correct the value |
| `VAL-020` | Invalid amount | Not a number, or negative | Correct the value |
| `VAL-021` | Hours out of range | Hours below zero or above 400 in a period | Correct the value |
| `VAL-022` | Amount above configured limit | Exceeds the per-payment limit on the contract | Approve manually, or request a limit change |
| `VAL-030` | Unknown cost centre | The cost centre does not exist | Create the cost centre, or clear the field |
| `VAL-031` | Note too long | Over 35 characters | Shorten the note |

## Employee record errors — a problem in the employee master

These reject the row too, but **the file is not the problem**. The row pointed at an employee
whose stored record cannot be paid. Correcting the file will not help; the employee master has
to be fixed.

| Code | Message | Cause | Resolution |
| --- | --- | --- | --- |
| `VAL-014` | Bank account is not a valid IBAN | The stored bank account does not pass IBAN validation | Update the employee's bank account in the master. See SALDO-DOC-0015 |
| `VAL-015` | Bank account country not supported | IBAN country code outside the customer's configured set | Contact support to extend the country set |
| `VAL-016` | No bank account on record | The employee has no bank account stored | Add one in the employee master |
| `VAL-017` | Contract not current | The employee's contract had ended before the pay period | End-date the employee, or extend the contract |
| `VAL-018` | Invalid personal number | The stored personal number does not match `NNNNNN/NNNN` | Correct it in the employee master |

## Downstream errors

Raised after validation, during disbursement.

| Code | Message | Cause | Resolution |
| --- | --- | --- | --- |
| `PAY-101` | Rejected by the banking partner | The receiving bank refused the credit | Verify the account with the employee |
| `PAY-102` | Insufficient funds on the funding account | The customer's funding account lacks cover | Fund the account and retry the run |
| `PAY-103` | Cut-off missed | Approved after the cut-off for the requested pay date | Approve earlier, or accept the next value date |

## Notes for support

- A run that reports rejections is **not** a platform incident. Rejections are the system
  working as designed. Only raise an incident if rows are rejected that conform to the
  specification.
