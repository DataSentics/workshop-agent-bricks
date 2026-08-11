# Service Description — Saldo

*[AI Explanation]: What Saldo is, which modules make it up, and what falls outside the service.
This is the definitive statement of scope; customer contracts refer to it rather than repeating
it.*

**Document ID:** SALDO-DOC-0001
**Applies to:** All Saldo plans
**Version:** 4.0
**Effective:** 1 January 2026
**Owner:** Product

---

## 1. What Saldo is

Saldo is cloud accounting software for companies operating in the Czech Republic and Slovakia.

It covers the work a finance department does month after month: keeping the books, issuing and
chasing invoices, paying employees, filing returns, and reconciling everything against the bank.

Customers run their own finances in Saldo. It is software, not an outsourced accounting service
— Saldo provides the system and applies the statutory rules, and the customer's finance team
does the work in it.

## 2. Modules

Customers subscribe to the modules they need. Which ones apply to a given customer is recorded
in their contract.

### Bookkeeping

The general ledger and everything on top of it: chart of accounts, journals, accruals, the VAT
ledger, fixed asset register, and the statutory financial statements.

### Invoicing

Issued and received invoices, recurring billing, credit notes, payment matching against bank
statements, and reminders for overdue receivables.

### Payroll

Employee records and contracts, monthly submission of hours and variable pay, gross-to-net
calculation with statutory deductions, payslips, salary payments, and the statutory payroll
reports.

### Tax

VAT returns, control statements, road tax and corporate income tax preparation, with submission
files in the formats the tax administration accepts.

### Banking

Bank account connections, automatic statement import, outgoing payment execution through
Saldo's banking partner, and reconciliation back to the ledger.

## 3. Channels

| Channel | Standard | Professional | Enterprise |
| --- | --- | --- | --- |
| Web application | yes | yes | yes |
| SFTP | no | yes | yes |
| API | no | yes | yes |

Availability targets and service credits are in the *Service Level Agreement*
(SALDO-DOC-0040). Support hours are in the *Support Policy* (SALDO-DOC-0041). Prices are in the
*Fee Schedule* (SALDO-DOC-0031).

## 4. What is not included

These are listed because they are the boundaries most often assumed to be inside the service.

- **Advice.** Saldo does not provide tax, legal, accounting or HR advice. Saldo applies the
  statutory rules; the decisions remain the customer's.
- **Bookkeeping as a service.** Saldo does not keep the customer's books for them. Customers who
  want that engage an accounting firm, which can be given access to their Saldo account.
- **Banking.** Saldo is not a bank and does not hold customer funds. Payments are executed by
  Saldo's banking partner from the customer's own accounts.
- **Maintaining customer data.** Saldo stores and validates what customers enter, including
  employee records. Keeping it correct is the customer's responsibility.
- **Time and attendance.** Recording shifts, clocking and absence approval is not part of the
  service. Customers may import the resulting hours into Payroll.
- **Countries other than the Czech Republic and Slovakia.** Entities and employees elsewhere
  are out of scope.

## 5. What the service depends on

Saldo does not control these, and cannot deliver without them:

- The accuracy of the data the customer maintains
  supplier details
- The customer completing approvals before the relevant cut-off
- The customer's bank accounts being funded before a payment date
- The availability of Saldo's banking partner, and of the tax administration's filing systems

## 6. Related documents

- *Payroll Run Guide* — SALDO-DOC-0008
- *Payroll Input File — Format Specification* — SALDO-DOC-0012
- *Managing Employee Data* — SALDO-DOC-0015
- *Service Level Agreement* — SALDO-DOC-0040
- *Fee Schedule* — SALDO-DOC-0031
