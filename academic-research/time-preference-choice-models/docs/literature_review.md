# Literature review: time preferences, from discount functions to machine learning

This is a structured map of the research the project builds on, organised around the questions in the project description: why people so often take a smaller reward now over a larger one later, how that choice is best modelled, and how far it can be shaped. Each entry records the question, the data and method, the main finding in my own words, and what it means for this project. The same entries are in [literature.csv](literature.csv) for sorting and filtering.

Every reference below was checked against the publisher, a university repository or RePEc in November 2026, except Samuelson (1937) and Mazur (1987), which are cited from standard textbook references.

## 1. Discount functions

| Paper | Question | Data and method | Finding | Relevance here |
|---|---|---|---|---|
| Samuelson (1937), *Review of Economic Studies* 4(2), 155–161 | How to represent preferences over time in one utility measure | Theory | Proposed discounted utility with a constant per-period rate (exponential discounting), adopted for decades as the standard model | The exponential model in `models.py` |
| Mazur (1987), in *Quantitative Analyses of Behavior*, Vol. 5 | What function describes how the value of a delayed reward falls with delay | Adjusting-delay procedure with animals | Value falls hyperbolically, V = A / (1 + kD): steep at short delays, flat at long ones | The hyperbolic model, and the k parameter used throughout |
| Laibson (1997), *Quarterly Journal of Economics* 112(2), 443–477 | How present bias shapes saving when commitment is possible | Theory and calibration | A two-parameter (beta-delta) form captures present bias tractably and explains demand for illiquid assets as self-commitment | The quasi-hyperbolic model; beta is the present-bias parameter |

## 2. Anomalies that a single discount rate cannot explain

| Paper | Question | Data and method | Finding | Relevance here |
|---|---|---|---|---|
| Kirby & Maraković (1996), *Psychonomic Bulletin & Review*, 100–104, doi:10.3758/BF03210748 | Is the discount rate independent of reward size? | 621 participants, choices between immediate and delayed rewards in three amount bands | Discount rates fall as amounts grow (the magnitude effect) | The simulation builds in a magnitude effect; `effects.magnitude_effect` tests for it within subjects |
| Frederick, Loewenstein & O'Donoghue (2002), *Journal of Economic Literature* 40(2), 351–401 | What does the evidence say about time discounting overall? | Review | Estimated discount rates vary enormously across studies and methods, and many anomalies contradict the discounted-utility model | Motivates comparing several models instead of assuming one |
| Read, Frederick, Orsel & Rahman (2005), *Management Science* 51(9), 1326–1335 | Does describing time as a calendar date rather than a delay change discounting? | Four experiments, choice and matching tasks | Discount rates are lower with calendar dates, and the discount function looks much less hyperbolic (the date/delay effect) | The between-subjects framing treatment in the simulated experiment |

## 3. Heuristics instead of discount functions

| Paper | Question | Data and method | Finding | Relevance here |
|---|---|---|---|---|
| Ericson, White, Laibson & Cohen (2015), *Psychological Science* 26(6), 826–833 | Do simple heuristics predict money-earlier-or-later choices better than discounting models? | Out-of-sample, cross-validated comparison of heuristic and discounting models | Heuristics that weigh absolute and relative differences in money and time (ITCH) predicted better than exponential and hyperbolic discounting | The ITCH model and the cross-validated comparison design |

## 4. Shaping time preferences

| Paper | Question | Data and method | Finding | Relevance here |
|---|---|---|---|---|
| Hershfield, Goldstein, Sharpe, Fox, Yeykelis, Carstensen & Bailenson (2011), *Journal of Marketing Research* 48(SPL), S23–S37 | Does making the future self vivid increase patience? | Experiments with age-progressed renderings of participants' own faces | Participants who saw their future selves more often chose later, larger rewards | A second family of interventions, beside framing, for a follow-up study |
| Read et al. (2005), above | | | Date framing works as a low-cost nudge towards patience | The treatment the simulation tests |

## 5. Machine learning as a benchmark for theory

| Paper | Question | Data and method | Finding | Relevance here |
|---|---|---|---|---|
| Peysakhovich & Naecker (2017), *Journal of Economic Behavior & Organization* 133, 373–384 | Can ML tell us how good behavioural models of choice under risk and ambiguity are? | Compare economic models with ML predictors on choice data | ML gives an upper bound on explainable variation. Under risk, standard models came close; under ambiguity they fell well short | The idea of benchmarking theory against ML |
| Fudenberg, Kleinberg, Liang & Mullainathan (2022), *Journal of Political Economy* 130(4), 956–990 | How much of the predictable variation in data does a model capture? | Define completeness and apply it to three experimental-economics problems | Completeness varies widely across established models, which shows where better theory could still help and where new features are needed | The completeness metric used in `evaluate.py` |

## 6. Overview

| Paper | Question | Data and method | Finding | Relevance here |
|---|---|---|---|---|
| Ericson & Laibson (2018), *Intertemporal Choice*, NBER Working Paper 25358 | Where does the field stand? | Review | The open question is no longer whether exponential discounting fits, but which models best explain the many deviations from it | Frames the model comparison |

## What the review suggests for the project

1. Compare several models out of sample, not by in-sample fit. Ericson et al. (2015) show the ranking can change once models have to predict new choices.
2. Report how much predictable variation each model captures, not only which model wins. Completeness (Fudenberg et al. 2022) separates "this theory is slightly worse than ML" from "this theory misses most of what is predictable".
3. Treat the framing manipulation as a test of shaping, with an effect size, a confidence interval and a check that results hold with and without exclusions.
4. With about 60 choices per person, individual estimates are noisy. Pooling information across people, as ML does implicitly and empirical Bayes does explicitly, should matter as much as the choice of functional form. The results bear this out.

## Gaps for future reading

- Hierarchical Bayesian estimation of discounting models, as a principled version of the empirical-Bayes shrinkage used here.
- Attribute-based models beyond ITCH, and recent work linking heuristic coefficients to discounting parameters.
- Text-based measures of time orientation in real social-media data, including the ethics of collecting it under the GDPR.
