# Service Level Agreement

*[AI Explanation]: What Saldo promises about keeping the service running, how that is measured, and what a
customer is owed if we fall short. Applies to every customer unless their contract says
otherwise.*

**Document ID:** SALDO-DOC-0040
**Version:** 3.0
**Effective:** 1 January 2026
**Owner:** Legal & Commercial
**Applies to:** All Saldo subscription plans

---

## 1. Scope

This agreement defines the availability Saldo commits to, how availability is measured, and
what a customer is entitled to when it is not met.

It covers the Saldo web application, the Payroll API and the SFTP channel.

## 2. Service plans

| Plan | Monthly availability target | Support hours | Service credits |
| --- | --- | --- | --- |
| Standard | 99.5% | Business hours | No |
| Professional | 99.9% | Extended hours | Yes |
| Enterprise | 99.95% | 24×7 | Yes |

Business hours are 09:00–17:00 CET, Monday to Friday, excluding Czech public holidays.
Extended hours are 07:00–19:00 CET, Monday to Friday.

## 3. How availability is measured

Availability is measured per calendar month, per service, as:

```
availability = (total minutes − unavailable minutes) / total minutes
```

A service is **unavailable** when it does not respond to requests, or returns errors caused by
a fault in the service, for a continuous period of five minutes or more.

The following are excluded from unavailable minutes:

- Scheduled maintenance announced at least five business days in advance
- Emergency maintenance announced as far ahead as is practicable
- Failures of the customer's own systems or network
- Failures of a banking partner outside Saldo's control
- Suspension for non-payment or for breach of the acceptable use policy

## 4. Service credits

Where the target is missed on a plan that includes credits, the customer may claim:

| Measured monthly availability | Credit |
| --- | --- |
| Below target, at or above 99.0% | 5% of the monthly fee |
| Below 99.0%, at or above 98.0% | 10% of the monthly fee |
| Below 98.0%, at or above 95.0% | 15% of the monthly fee |
| Below 95.0% | 25% of the monthly fee |

Credits are capped at 25% of the monthly fee for the affected month. They are issued against a
future invoice and are not paid in cash.

## 5. Claiming a credit

The customer must claim in writing within **30 days** of the end of the affected month, quoting
the relevant support case. Saldo confirms or rejects the claim within 10 business days.

## 6. What service credits do not cover

This section exists because it is the most frequent source of disagreement.

Service credits compensate for the **service being unavailable**. They do not apply to:

- **Rejected records.** Payment rows rejected at validation are the service operating
  correctly. A run that completes with rejected rows is not a period of unavailability, however
  disruptive the outcome. This applies regardless of how many rows were rejected.
- **Incorrect customer data.**
- **Missed cut-off times** where the customer approved a run late.
- **Delays at a banking partner** once instructions have been submitted successfully.
- **Loss of business, lost profit or reputational harm**, which are excluded in all cases.

Where a customer has suffered disruption that falls outside this section, the account manager
may offer a goodwill gesture. That is a commercial decision, is not an admission of breach, and
sits outside this agreement.

## 7. Related documents

- *Support Policy* — SALDO-DOC-0041
- *Fee Schedule* — SALDO-DOC-0031
