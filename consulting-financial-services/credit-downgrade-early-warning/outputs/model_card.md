# Model card: credit downgrade early warning

## Purpose

Rank rated corporate issuers by the chance of a downgrade in the next three months, so credit analysts can decide which names to review first. The model supports a human review; it does not take rating or lending decisions.

## Data

Synthetic: 360 European issuers, 65,908 news articles in English and German from 2022-01 to 2026-09, quarterly financials, share prices and agency rating actions. No real company or person appears.

## Design

1. Article model: TF-IDF on words, word pairs and character n-grams, logistic regression. Issuer names, sectors, cities, quarters and numbers are masked, and words after a negation are marked. Training articles get out-of-fold scores (5 folds grouped by issuer).
2. Issuer-month model: gradient boosting on rating and outlook, financials and share price, keyword counts and the aggregated article scores.

Training: 12,930 issuer-months up to 2025-03. Test: 4,310 issuer-months from 2025-07, after a three-month gap so no training label overlaps the test period. Base rate in test: 3.9%.

## Results (out of time)

| model                |   roc_auc |   pr_auc |   brier |   alerts_per_month |   alert_precision |   downgrades |   caught |   event_recall |   median_lead_months |
|:---------------------|----------:|---------:|--------:|-------------------:|------------------:|-------------:|---------:|---------------:|---------------------:|
| Outlook only         |    0.636  |   0.073  |  0.0363 |            39.4167 |            0.1311 |           65 |       30 |         0.4615 |                    3 |
| Ratings + financials |    0.64   |   0.0814 |  0.0373 |            15      |            0.1333 |           65 |       15 |         0.2308 |                    3 |
| + keyword rules      |    0.73   |   0.1869 |  0.0345 |            15      |            0.25   |           65 |       27 |         0.4154 |                    2 |
| + NLP news scores    |    0.7779 |   0.2577 |  0.0331 |            15      |            0.2889 |           65 |       32 |         0.4923 |                    2 |

With the same review budget of 15 names a month, the full model's alerts were right 29% of the time against 25% for keyword rules, and it flagged 49% of downgrades in the three months before they happened.

Feature groups, drop in PR-AUC when shuffled:

| feature_group              |   pr_auc_drop |     sd |
|:---------------------------|--------------:|-------:|
| NLP news scores            |        0.2074 | 0.0042 |
| Rating and outlook         |        0.074  | 0.0097 |
| Keyword counts             |        0.0169 | 0.0099 |
| Financials and share price |        0.0032 | 0.0172 |

## Validation

| test                                           | passed   | detail                                                     |
|:-----------------------------------------------|:---------|:-----------------------------------------------------------|
| Invariance: 20 company names                   | 20/20    | score range 0.00e+00                                       |
| Negation: denial scores lower than the problem | 4/5      | 0.71->0.71; 0.68->0.67; 0.72->0.69; 0.63->0.68; 0.69->0.67 |
| Directional: red flag raises score             | 2/3      | 0.50->0.57; 0.50->0.61; 0.59->0.55                         |
| Unseen paraphrases classified correctly        | 7/12     | AUC 0.64                                                   |

| language   |   articles |   positive_share |   roc_auc |   pr_auc |
|:-----------|-----------:|-----------------:|----------:|---------:|
| de         |       5763 |            0.043 |     0.692 |    0.103 |
| en         |      11673 |            0.059 |     0.68  |    0.132 |

## Limits

- The news is generated from templates. A bag-of-words model learns those phrasings well and generalises poorly to new wording (see the unseen-paraphrase test). On real news it would need human-labelled articles and most likely a multilingual transformer or an LLM classifier, validated with the same behavioural tests.
- Denials are scored as risky. In this data that is correct (issuers denying problems were downgraded far more often than average), but it should be checked on real data before anyone relies on it.
- Scores are rankings first. Calibrated probabilities would need a calibration step on recent data.
- One agency, one rating scale, monthly granularity.
