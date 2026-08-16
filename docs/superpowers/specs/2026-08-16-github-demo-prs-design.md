# ChangeGuard GitHub Demo Pull Requests

## Goal

Keep five `[Demo]` pull requests open in `tkim602/ChangeGuard`. Each pull request presents an immutable issue and patch, identifies the original repository and issue, states whether FT06 saw the task during training or evaluation, and contains one maintained ChangeGuard report comment.

The demo must use the same collection and scoring path as an ordinary pull request. It must not write to an upstream repository.

## Selected approach

Use real GitHub pull request diffs rather than embedded patch manifests.

For each case:

1. Create a case-specific base branch from the current `main` branch and add the original versions of only the files touched by the source patch in a preparation commit.
2. Create a head branch that applies the frozen source patch.
3. Create a local ChangeGuard issue containing the frozen source issue text.
4. Open a `[Demo]` pull request from the head branch to its case-specific base branch.
5. Link the local issue from the pull request body so the existing collector uses the issue text.
6. Record the source repository, original issue identifier, dataset source, FT06 exposure, frozen record ID, patch hash, and expected execution label in the pull request body.

This keeps the workflow files and trusted ChangeGuard implementation present on every pull request base while avoiding a full copy of each upstream repository. The pull request diff contains the original source patch because the preparation commit belongs to the base branch. The branches contain no upstream history and do not modify upstream GitHub projects.

## Demo set

Freeze five cases before model inference:

- Four tasks from the FT06 training split.
- One task from a frozen FT06 evaluation split.
- At least two expected PASS labels and two expected REVIEW labels.
- Five distinct upstream repositories where the source files and base revisions can be reconstructed.
- Source paths that do not overwrite ChangeGuard files.
- Public source repositories with license and source URLs recorded in the pull request.
- Every prompt must pass the exact 8,192-token preflight without truncation.

Selection may use split membership, label, repository diversity, patch size, file availability, and change category. It must not use FT06 demo scores. If a selected source cannot be reconstructed exactly, replace it before inference and record the reason locally.

## Automatic review flow

### Every pull request

The existing `pull_request` workflow runs deterministic inspection automatically with read-only permissions. It checks out trusted default-branch code and collects the pull request through the GitHub API at immutable base and head SHAs.

Input selection remains:

1. One linked issue referenced with `Fixes`, `Closes`, or `Resolves`.
2. Otherwise, the pull request title and description.
3. Missing useful context is reported as insufficient context, not low risk.

### Frozen FT06 model

The model workflow supports three trusted triggers:

- Automatic execution when a pull request title starts with `[Demo]` and the author is `tkim602`.
- Execution when a maintainer applies the `changeguard-model` label.
- Existing manual dispatch for recovery.

The automatic model path uses `pull_request_target`, checks out only the default branch, and reads the target pull request through the GitHub API. It never checks out or executes code from the pull request. Repository secrets are available only to the trusted workflow code. Concurrency is limited per pull request, stale runs are cancelled, Modal permits one GPU container, and the existing timeouts remain in force.

External contributors cannot trigger GPU use merely by opening or updating a pull request.

## Report copy

The maintained comment uses this order:

1. `ChangeGuard review`
2. Model signal and risk percentile, or a precise unavailable status.
3. Deterministic code-change findings.
4. Analysis gaps, when present.
5. Immutable base and head fingerprints in a collapsed section.
6. Advisory limitation.

Use no emoji, decorative badges, marketing claims, or conversational filler. Use `LOWER`, `ELEVATED`, and `HIGH` as plain status text. Do not call a patch safe. Replace the existing long rule formatting with concise file, severity, and finding text. One marker-delimited comment is updated in place.

The pull request body carries provenance and exposure. The model report does not repeat that table.

## Reuse by other repositories

Package the CPU collector and deterministic analyzer as a composite GitHub Action with a short example workflow. It requires only the caller's read-only `GITHUB_TOKEN` and works on ordinary `pull_request` events.

The hosted FT06 path is not offered as an unrestricted public service. Other repositories can use the CPU action without secrets. Model execution requires a separately configured backend and credentials until a budgeted, authenticated public service exists.

## Failure behavior

- Oversized prompt: model unavailable, no truncation.
- Missing issue and weak pull request description: insufficient context.
- Modal error or timeout: model unavailable, deterministic findings still published.
- Source reconstruction mismatch: do not create that demo pull request.
- Upstream API failure during preparation: retry preparation without changing the frozen selection rule.

## Verification

- Unit tests cover issue fallback, trusted model triggers, comment rendering, and no duplicate comment creation.
- Workflow tests assert default-branch checkout, no pull-request code execution, restricted permissions, timeouts, and concurrency.
- Each reconstructed source patch must match its frozen patch SHA before its branches are pushed.
- Each open demo pull request must complete the CPU workflow and one FT06 model run.
- Final audit lists five open `[Demo]` pull requests, five report comments, their exposure classes, workflow URLs, and model statuses.

## Out of scope

- Writing comments to upstream repositories.
- Automatic merge, approval, or blocking.
- Public access to the owner's Modal credentials.
- Selecting demo cases after observing FT06 scores.
- New fine-tuning or model changes.
