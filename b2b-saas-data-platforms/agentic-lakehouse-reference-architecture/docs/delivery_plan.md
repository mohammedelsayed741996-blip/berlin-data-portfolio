# Delivery plan

Estimates for taking this reference architecture to a pilot with one Finance team (about 15 account managers). Person-days assume one solutions architect and one data engineer, with a Finance product owner available two hours a week.

| Phase | Scope | Estimate | Exit criterion |
|---|---|---|---|
| 0. Discovery | Questions account managers ask today, metric definitions with Finance, data access, security review kick-off | 5 days | Signed-off metric list and 40 real questions for the evaluation set |
| 1. Lakehouse | ERP exports to bronze, silver rules, gold marts, reconciliation checks, Glue and Athena | 10 days | Gold open receivables match the ERP to the cent for three month-ends |
| 2. Agent core | Semantic layer, tools, guard, approval queue on DynamoDB, Bedrock planner, tracing | 10 days | All core tasks pass with the Bedrock planner; red team shows no leaks |
| 3. Integration | Cognito with the company IdP, API, Lambda layer, CloudWatch alarms, email sending after approval | 8 days | End-to-end in a test account with real roles |
| 4. Pilot | Five account managers and two Finance users for four weeks, weekly review of traces and failed questions | 4 weeks elapsed, 6 days effort | Task success, approval rejection rate and time saved agreed with the product owner |

Total effort before the pilot: about 33 person-days, so roughly seven to eight weeks with two people part time.

## Running cost (pilot, estimate)
Bedrock tokens dominate. At about 6,000 input and 600 output tokens per question, 15 users asking 20 questions a working day comes to about 6,600 questions a month. Lambda, API Gateway, Athena (small scans) and DynamoDB together stay in the low tens of euros a month at that volume. Model prices change, so the cost per question is recorded in every trace rather than fixed in this plan.

## Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Metric definitions disputed between Finance and Sales | High | Phase 0 sign-off; definitions live in one file with tests |
| Model misreads paraphrased questions | Medium | Paraphrase set in the evaluation; gate on it once the Bedrock planner runs |
| Prompt injection through customer emails or documents | Medium | Untrusted wrapping, no tool can send anything without approval, red-team suite in CI |
| ERP export format changes | Medium | Bronze keeps raw files; silver rules fail loudly in reconciliation |
| Data residency questions from legal | Low | EU inference profile, Frankfurt region, no data leaves the AWS account |
| Users trust a wrong number | Medium | Answers cite the metric and filters used; traces let Finance check any answer |
