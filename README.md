# ChangeGuard

ChangeGuard is an advisory pull-request triage tool built around a frozen, fine-tuned Qwen2.5-Coder-7B verifier. Given a PR description and diff, it produces a review-priority signal and shows a separate set of deterministic code-change findings.

It does **not** approve a patch, auto-merge it, block it, or execute code from the PR.

## Why this project

AI coding agents can produce patches quickly, but deciding whether a patch actually solves the issue without introducing a regression is still hard. ChangeGuard tests a narrower question: can a relatively small verifier learn a useful patch-correctness signal and fit into a normal GitHub review workflow?

The current claim is intentionally limited. The verifier works best on data close to its training distribution and becomes less reliable as the distribution shift gets harder.

## Results

The main baseline is the same Qwen2.5-Coder-7B model used **zero-shot**, with the same prompt/scoring setup and frozen evaluation sets. This makes the comparison more useful than comparing against a different model family.

### ROC-AUC

| Evaluation setting | Zero-shot | Fine-tuned | Change |
|---|---:|---:|---:|
| Familiar held-out tasks | 0.6058 | **0.8200** | **+0.2142** |
| Unseen repositories | 0.5670 | **0.7479** | **+0.1809** |
| Unseen agent family | 0.5176 | **0.6751** | **+0.1575** |
| Shortcut-controlled hard cases | 0.5326 | **0.5972** | **+0.0645** |
| Independent external review set | 0.6191 | **0.6540** | **+0.0349** |

### Unsafe PR-AUC

| Evaluation setting | Zero-shot | Fine-tuned | Change |
|---|---:|---:|---:|
| Familiar held-out tasks | 0.9007 | **0.9656** | **+0.0649** |
| Unseen repositories | 0.8438 | **0.9121** | **+0.0684** |
| Unseen agent family | 0.5460 | **0.7080** | **+0.1620** |
| Shortcut-controlled hard cases | 0.5261 | **0.5900** | **+0.0639** |
| Independent external review set | 0.6030 | **0.6264** | +0.0233 |

The trend matters more than the best number. Fine-tuning gives a large gain on familiar held-out tasks and unseen repositories, but the gap gets smaller on harder shortcut-controlled and external data. For the external unsafe PR-AUC result, the bootstrap interval includes zero, so I do not treat that gain as conclusive.

A fuller breakdown, including confidence intervals, shortcut baselines, internal split names, and the archived DATA-04A stress test, is in [`docs/evaluations.md`](docs/evaluations.md).

The deterministic rules are **not** part of the model score. In a frozen A/B/C evaluation, combining the static rule signal with the learned score reduced unsafe PR-AUC on the shortcut-controlled set from **0.5900 to 0.5150** (delta **-0.0750**, 95% CI **[-0.0981, -0.0559]**). Because of that result, ChangeGuard keeps the two paths separate.

## Live replay demos

The open `[Demo]` pull requests replay historical real-world open-source issue/candidate-patch pairs through the deployed ChangeGuard workflow.

```mermaid
flowchart LR
    A[Historical open-source<br/>issue + candidate patch]
    B[Live GitHub Demo PR]
    C[Immutable PR input<br/>base SHA + head SHA]
    D[8K tokenizer preflight]
    E[Modal L40S]
    F[Frozen fine-tuned verifier]
    G[ChangeGuard review comment]

    A --> B --> C --> D --> E --> F --> G
```

These are deployment demos, not a generalization benchmark. Four are frozen training examples and one is a held-out example from the familiar evaluation distribution. Generalization is evaluated separately in the result tables above.

- [#13, more-itertools](https://github.com/tkim602/ChangeGuard/pull/13): SAFE reference, `LOWER` signal
- [#14, pandas](https://github.com/tkim602/ChangeGuard/pull/14): SAFE reference, `LOWER` signal
- [#15, pynetdicom](https://github.com/tkim602/ChangeGuard/pull/15): UNSAFE reference, `ELEVATED` signal
- [#16, moto](https://github.com/tkim602/ChangeGuard/pull/16): UNSAFE reference, `HIGH` signal
- [#17, flake8-comprehensions](https://github.com/tkim602/ChangeGuard/pull/17): SAFE reference, held-out example, `LOWER` signal

## Architecture

```mermaid
flowchart LR
    PR[GitHub PR<br/>issue description + immutable diff]

    PR --> MODEL[Frozen fine-tuned verifier]
    PR --> STATIC[Deterministic static inspection]

    MODEL --> RP[Risk percentile]
    RP --> SIGNAL[LOWER / ELEVATED / HIGH]

    STATIC --> FLAGS[Code-change findings]

    SIGNAL --> OUT[ChangeGuard review]
    FLAGS --> OUT
```

The two paths are independent:

- **Model signal:** `LOWER`, `ELEVATED`, or `HIGH`, derived from the frozen calibration distribution.
- **Code-change findings:** public API changes, auth/workflow/config changes, missing test changes, removed validation, dangerous execution patterns, and analysis gaps.
- **Failure behavior:** an oversized input or model failure is reported as unavailable, never as low risk.

A static finding can disagree with the model signal. For example, a patch can receive `LOWER` from the model while still being flagged because production Python changed without a test-file change. The finding is a review hint; it does not change the model percentile.

## Try it on your repository

### Read-only CPU inspection

The reusable action can be added to another GitHub repository. It reads the PR, inspects the diff without executing PR code, and writes the result to the Actions summary.

```yaml
name: ChangeGuard

on:
  pull_request:

permissions:
  contents: read
  issues: read
  pull-requests: read

jobs:
  inspect:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/setup-python@v7
        with:
          python-version: "3.12"
      - uses: tkim602/ChangeGuard@main
        with:
          github-token: ${{ github.token }}
          pull-request-number: ${{ github.event.pull_request.number }}
```

A complete example is in [`docs/examples/changeguard.yml`](docs/examples/changeguard.yml).

The reusable action is intentionally CPU-only. It runs the deterministic inspection, does not execute PR code, and does not post comments to the target PR. Once this repository is public, other public repositories can reference the action directly.

### Hosted model path

The GPU-backed verifier is currently **maintainer-gated**, not a public inference service. The adapter and calibration artifacts are not committed, and the Modal credentials stay in repository secrets.

For this repository, the model workflow can run on owner-authored `[Demo]` PRs, on a PR labeled `changeguard-model`, or through manual workflow dispatch. Arbitrary PR authors cannot spend GPU credit just by opening a PR.

```mermaid
flowchart LR
    A[PR description + diff]
    B[Exact 8K preflight]
    C[Modal L40S]
    D[Frozen adapter]
    E[Calibrated risk percentile]
    F[One PR comment]

    A --> B --> C --> D --> E --> F
```

PR text and the diff are sent to Modal when the model workflow runs. Do not use the GPU path for code that cannot leave GitHub.

## CI and GitHub Actions

There are three separate workflows because they serve different purposes.

| Workflow | Trigger | Purpose |
|---|---|---|
| [`ci.yml`](.github/workflows/ci.yml) | push to `main`, pull request | installs the package and runs the test suite on Python 3.12 |
| [`changeguard-evidence.yml`](.github/workflows/changeguard-evidence.yml) | pull request | read-only PR collection and deterministic inspection; uploads JSON/Markdown artifacts |
| [`changeguard-full.yml`](.github/workflows/changeguard-full.yml) | gated PR event or manual dispatch | exact tokenizer preflight, Modal model inference, report rendering, and one marked PR comment |

The model workflow uses a per-PR concurrency group with `cancel-in-progress: true`, so a newer run replaces an older one for the same PR. The GitHub job has a 20-minute timeout and the Modal worker has a 15-minute timeout. If preflight or model execution fails, ChangeGuard reports the model as unavailable instead of quietly returning a low-risk result.

## Local development

The CPU analyzer has no runtime package dependencies beyond Python itself.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
```

Offline analysis accepts a collected PR payload containing `patch`, `before_after`, `base_sha`, and `head_sha`:

```bash
python -m changeguard.github_demo analyze \
  --input pr.json \
  --output changeguard.json \
  --markdown changeguard.md
```

## Reproducibility and limits

- Base model: `Qwen/Qwen2.5-Coder-7B-Instruct`, pinned revision `c03e6d358207e414f1eca0bb1891e29f1db0e242`.
- The deployed adapter, adapter config, prompt, and calibration artifacts are SHA-256 checked before scoring.
- Inputs above 8,192 tokens are rejected without truncation.
- The model produces a calibrated review-priority signal, not a merge decision.
- The static analyzer does not execute code from the PR.
- Training/evaluation datasets, model weights, and private experiment archives are not included in this repository.

The deployed checkpoint is called `FT06` in the internal experiment record and a few source files. That name is kept for reproducibility, but the README uses the more descriptive term **fine-tuned verifier**.

A short PDF project report is planned separately for the experiment timeline, dataset construction, ablations, failure cases, and evaluation details so this README can stay focused on the working system.
