# ChangeGuard

ChangeGuard is an advisory GitHub pull-request triage demo built around a frozen, fine-tuned Qwen2.5-Coder-7B verifier. It ranks a PR for human review from its issue description and diff, while showing transparent code-change flags separately.

It does **not** approve safety, auto-merge, block a PR, or execute code from the PR.

## Why this project

The project tests whether a relatively small verifier can learn useful patch-correctness signals. The frozen FT06 seed-17 model is strongest on familiar and held-out repositories; performance drops under harder distribution shifts, so the product claim is deliberately narrow: prioritize review for repositories and change patterns close to the validated domain.

| Frozen evaluation split | ROC-AUC | Unsafe PR-AUC |
|---|---:|---:|
| ID | 0.8200 | 0.9656 |
| Repo-OOD | 0.7479 | 0.9121 |
| Policy-OOD | 0.6751 | 0.7080 |
| Hard-match | 0.5972 | 0.5900 |
| SWE-Review external | 0.6540 | 0.6264 |
| DATA-04A | 0.5151 | 0.3927 |

The deterministic rules are not part of the model score. A frozen A/B/C evaluation found that combining them with FT06 reduced hard-match unsafe PR-AUC from 0.5900 to 0.5150 (delta −0.0750; 95% CI [−0.0981, −0.0559]). ChangeGuard therefore exposes rules only as review context.

## What runs on a PR

```text
PR description + immutable diff ──> frozen FT06 verifier ──> model signal
                   │
                   └──────────────> static inspection ─────> code-change flags
```

- **Model signal:** `LOWER`, `ELEVATED`, or `HIGH`, derived from the frozen FT06 calibration distribution.
- **Code-change flags:** public API changes, auth/workflow/config changes, missing test changes, removed validation, dangerous execution patterns, and analysis gaps.
- **Failure behavior:** an oversized input or model failure is reported as unavailable, never as low risk.

## GitHub Actions

[`changeguard-evidence.yml`](.github/workflows/changeguard-evidence.yml) runs automatically on every PR using a GitHub-hosted CPU. It checks out the default branch, fetches immutable base/head SHAs through the GitHub API, inspects the diff without running PR code, and publishes JSON and Markdown artifacts. It needs no external secrets.

[`changeguard-full.yml`](.github/workflows/changeguard-full.yml) is a maintainer-triggered workflow. It repeats the CPU inspection, performs the exact 8K tokenizer preflight, invokes the frozen adapter on a scale-to-zero Modal L40S worker, and updates one marked PR comment. The GPU exists only for the invocation.

### Enable the frozen model workflow

The adapter and calibration data are intentionally not committed. From a trusted machine:

```bash
python3 -m pip install modal==1.5.2
modal setup
MODAL_ENVIRONMENT=changeguard-demo python3 scripts/upload_ft06_adapter.py \
  --adapter /path/to/ft06/adapter \
  --calibration-predictions /path/to/calibration_verifier.jsonl
```

Add `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET` as repository Actions secrets. Then run **ChangeGuard frozen FT06 model** from the Actions tab with a PR number.

The model workflow is maintainer-triggered, targets the isolated `changeguard-demo` Modal environment, permits one GPU at a time, and has a 15-minute Modal timeout plus a 20-minute Actions timeout. Visitors cannot spend GPU credit by opening a PR.

PR text and the diff are sent to Modal during this manual run. Do not use the model workflow for code that cannot leave GitHub.

## Local checks

The CPU analyzer uses only the Python standard library:

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
- The adapter, prompt, and calibration artifacts are SHA-256 gated before scoring.
- Inputs above 8,192 tokens are rejected without truncation.
- The demo is advisory and is not a substitute for tests, code review, or security analysis.
- Training/evaluation datasets, model weights, and private experiment archives are not part of this repository.
