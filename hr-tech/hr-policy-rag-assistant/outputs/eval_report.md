# Evaluation report

Hand-written questions: 93 (48 dev, 45 test). The decline threshold (0.17) was chosen on dev; the numbers below are for the test split.

| Measure | Test | Dev | Gate |
|---|---:|---:|---:|
| Right passage ranked first | 73% | 85% |  |
| Right passage in top 3 | 95% | 98% | >= 90% |
| Mean reciprocal rank | 0.84 | 0.91 |  |
| Answer correct (cites the right passage and contains the facts) | 70% | 82% | >= 65% |
| Answerable questions wrongly declined | 3% | 5% |  |
| Out-of-scope and restricted questions declined | 100% | 100% | >= 95% |
| Restricted passages cited | 0 | 0 | = 0 |
| Latency, 95th percentile (ms) | 3 | 3 |  |

## Retrievers on the test split

| retriever   | synonyms   |   hit_at_1 |   hit_at_3 |   mrr |   answer_correct |
|:------------|:-----------|-----------:|-----------:|------:|-----------------:|
| bm25        | False      |      0.73  |      0.919 | 0.822 |            0.703 |
| bm25        | True       |      0.703 |      0.946 | 0.823 |            0.676 |
| tfidf       | False      |      0.73  |      0.919 | 0.826 |            0.703 |
| tfidf       | True       |      0.757 |      0.946 | 0.853 |            0.73  |
| hybrid      | False      |      0.73  |      0.919 | 0.817 |            0.703 |
| hybrid      | True       |      0.73  |      0.946 | 0.835 |            0.703 |

## Test questions where the right passage was not cited

| Question | Expected | Rank |
|---|---|---:|
| Can I take leftover vacation days into next year? | HR-01#carry-over | 2 |
| Is there paid leave when a parent dies? | HR-01#special-leave | 5 |
| Do I have to tell my boss what illness I have? | HR-02#reporting-sick | 3 |
| Do I have to send the Krankmeldung paper to HR myself? | HR-02#medical-certificate | 3 |
| How long is the break on a shift? | HR-03#regular-working-time | 2 |
| Can people in logistics do home office? | HR-05#who-can-work-remotely | 2 |
| Does HR store my diagnosis when I'm sick? | HR-10#what-we-process | 2 |
| How fast will I hear back after a whistleblower report? | HR-11#what-happens-next | 3 |
| Can I get in trouble for reporting a safety problem? | HR-11#protection | 5 |
