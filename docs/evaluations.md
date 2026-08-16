# Evaluation notes

This page keeps the detailed names and numbers behind the shorter result summary in the README.

The main baseline is the same Qwen2.5-Coder-7B base model used without fine-tuning. The prompt format, scoring rule, and frozen evaluation sets are kept the same, so the comparison is intended to show what changed after fine-tuning rather than what changed after switching models.

Confidence intervals are based on 10,000 paired nonparametric bootstrap resamples over the frozen seed-17 predictions. They measure uncertainty from the evaluation sample, not variation across training seeds.

## Zero-shot base model vs fine-tuned verifier

### ROC-AUC

| Evaluation setting | Internal split | Zero-shot | Fine-tuned | Change | 95% CI for change |
|---|---|---:|---:|---:|---:|
| Familiar held-out tasks | `id_test` | 0.6058 | 0.8200 | +0.2142 | [+0.1867, +0.2418] |
| Unseen repositories | `repo_ood` | 0.5670 | 0.7479 | +0.1809 | [+0.1554, +0.2071] |
| Unseen agent family | `policy_ood` | 0.5176 | 0.6751 | +0.1575 | [+0.1115, +0.2024] |
| Shortcut-controlled hard cases | `hard_match_test` | 0.5326 | 0.5972 | +0.0645 | [+0.0325, +0.0959] |
| Independent external review set | `swe_review` | 0.6191 | 0.6540 | +0.0349 | [+0.0003, +0.0691] |

### Unsafe PR-AUC

| Evaluation setting | Internal split | Zero-shot | Fine-tuned | Change | 95% CI for change |
|---|---|---:|---:|---:|---:|
| Familiar held-out tasks | `id_test` | 0.9007 | 0.9656 | +0.0649 | [+0.0546, +0.0756] |
| Unseen repositories | `repo_ood` | 0.8438 | 0.9121 | +0.0684 | [+0.0565, +0.0802] |
| Unseen agent family | `policy_ood` | 0.5460 | 0.7080 | +0.1620 | [+0.1178, +0.2022] |
| Shortcut-controlled hard cases | `hard_match_test` | 0.5261 | 0.5900 | +0.0639 | [+0.0327, +0.0955] |
| Independent external review set | `swe_review` | 0.6030 | 0.6264 | +0.0233 | [-0.0151, +0.0613] |

The pattern is more useful than any single score. Fine-tuning gives a clear gain on familiar held-out tasks, new repositories, and the held-out agent family. The gain becomes much smaller on the shortcut-controlled set and on the independent external data. For external unsafe PR-AUC, the interval includes zero, so that improvement is not treated as conclusive.

## What the evaluation settings mean

**Familiar held-out tasks (`id_test`)** use held-out examples from the same overall data distribution as training. They test whether the verifier learned the task at all without requiring a major distribution shift.

**Unseen repositories (`repo_ood`)** come from repositories excluded from training. This tests whether the verifier can carry what it learned to a new codebase.

**Unseen agent family (`policy_ood`)** uses candidate patches from an agent-generation family held out from training. The internal filename says `policy_ood`, but the intended interpretation is an agent-family shift.

**Shortcut-controlled hard cases (`hard_match_test`)** deliberately make SAFE and UNSAFE examples look similar on easy structural cues such as changed-file count and patch size. This split is meant to make simple shortcuts less useful.

**Independent external review set (`swe_review`)** comes from a separate external dataset and is the furthest transfer test in the current evaluation.

## Shortcut controls

On the shortcut-controlled set, simple structural and metadata baselines were close to chance:

| Baseline | ROC-AUC |
|---|---:|
| Structural shortcut | 0.4974 |
| Metadata shortcut | 0.5011 |
| Zero-shot 7B | 0.5326 |
| Fine-tuned verifier | 0.5972 |

This is evidence that the fine-tuned score is not explained only by obvious features such as patch length or repository metadata. The absolute score is still modest, which is why PatchCheck is framed as review triage rather than a universal correctness verifier.

## Deterministic rules

The static rules are not part of the learned model score. A frozen A/B/C evaluation on the shortcut-controlled set found that combining deterministic signals with the learned score reduced unsafe PR-AUC from 0.5900 to 0.5150, a change of -0.0750 with a 95% CI of [-0.0981, -0.0559]. The deployed demo therefore keeps static findings separate and shows them only as review context.

## DATA-04A archive

DATA-04A is kept here as a historical stress-test result, but it is not part of the current official result table or model-selection evidence.

It contains 47 examples. ROC-AUC was 0.5151 for the fine-tuned verifier versus 0.4980 zero-shot, a change of +0.0171 with a 95% CI of [-0.2134, +0.2591]. Unsafe PR-AUC was 0.3927 versus 0.4218 zero-shot, a change of -0.0292 with a 95% CI of [-0.2489, +0.1899]. The sample is too small and the intervals are too wide to support a useful positive claim.

## Internal experiment name

The deployed fine-tuned checkpoint is referred to as `FT06` in the private experiment record and some source files. That name is kept only where it helps reproduce the exact experiment; the README refers to it simply as the frozen fine-tuned verifier.

Earlier model and data experiments used different datasets and evaluation protocols, so their headline metrics are not placed next to the current model as if they were controlled comparisons. The zero-shot 7B baseline is the main comparison because it shares the frozen evaluation setup.
