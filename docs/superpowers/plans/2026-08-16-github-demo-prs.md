# GitHub Demo Pull Requests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish five open `[Demo]` pull requests that exercise the frozen FT06 model through a trusted automatic GitHub workflow, while making the CPU analyzer reusable by other repositories.

**Architecture:** Ordinary pull requests continue to run a read-only CPU workflow. A trusted `pull_request_target` path runs FT06 only for owner-authored `[Demo]` pull requests or a maintainer-applied `changeguard-model` label, always using default-branch workflow code and immutable API snapshots. Demo base branches carry reconstructed pre-patch files; head branches contain the frozen patch, so GitHub exposes a real patch without touching upstream repositories.

**Tech Stack:** Python 3.12 standard library, pytest, GitHub Actions, GitHub REST API, Modal 1.5.2, frozen FT06 QLoRA adapter.

---

### Task 1: Tighten context handling and report copy

**Files:**
- Modify: `src/changeguard/github_demo.py`
- Modify: `src/changeguard/triage.py`
- Modify: `tests/test_github_demo.py`
- Modify: `tests/test_triage.py`

- [ ] **Step 1: Write failing tests for context status and restrained Markdown**

Add assertions that a linked issue records `LINKED_ISSUE`, an empty fallback records `INSUFFICIENT_CONTEXT`, and rendered reports use `## ChangeGuard review`, contain no emoji or em dash, and keep the marker required for comment updates.

- [ ] **Step 2: Run focused tests and confirm failure**

Run: `pytest tests/test_github_demo.py tests/test_triage.py -q`

Expected: failures for the new context fields and report heading.

- [ ] **Step 3: Implement minimal context metadata and copy changes**

Return `issue_source` and `context_status` from collection, pass them into the result metadata, and gate model presentation as unavailable when the input has no useful issue text. Render concise finding lines as `severity, message (file:line)` without decorative rule identifiers in the main list.

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/test_github_demo.py tests/test_triage.py -q`

Expected: all focused tests pass.

### Task 2: Add trusted automatic FT06 execution

**Files:**
- Modify: `.github/workflows/changeguard-full.yml`
- Modify: `tests/test_github_demo.py`

- [ ] **Step 1: Write failing workflow assertions**

Assert that the model workflow declares `pull_request_target` for `opened`, `reopened`, `synchronize`, and `labeled`; keeps `workflow_dispatch`; checks out the default branch; accepts owner-authored `[Demo]` pull requests; accepts the `changeguard-model` label; and defines per-PR concurrency.

- [ ] **Step 2: Run the workflow test and confirm failure**

Run: `pytest tests/test_github_demo.py::test_github_workflows_are_safe_and_pinned -q`

Expected: failure because the trusted automatic trigger is absent.

- [ ] **Step 3: Implement the workflow trigger**

Use one `score` job with a job-level condition for manual dispatch, owner-authored `[Demo]` events, or a `changeguard-model` labeled event. Resolve the pull request number from either event payload or dispatch input. Keep default-branch checkout, existing timeouts, one comment marker, and no pull-request code execution.

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/test_github_demo.py -q`

Expected: all GitHub demo tests pass.

### Task 3: Package the CPU analyzer for other repositories

**Files:**
- Create: `action.yml`
- Create: `docs/examples/changeguard.yml`
- Modify: `README.md`
- Modify: `tests/test_github_demo.py`

- [ ] **Step 1: Write a failing action contract test**

Assert that `action.yml` is a composite action, requires a GitHub token and pull request number, runs only the collector and CPU analyzer, appends the report to `GITHUB_STEP_SUMMARY`, and contains no Modal credentials or model invocation.

- [ ] **Step 2: Run the action contract test and confirm failure**

Run: `pytest tests/test_github_demo.py -q`

Expected: failure because `action.yml` does not exist.

- [ ] **Step 3: Add the minimal composite action and consumer example**

The consumer workflow runs on `pull_request`, grants read-only contents/issues/pull-request permissions, and calls `tkim602/ChangeGuard@main` with `${{ github.token }}` and `${{ github.event.pull_request.number }}`. Document that external reuse requires the repository to be public and that the model workflow is not an unrestricted hosted service. Do not change repository visibility without separate user approval.

- [ ] **Step 4: Run the full local suite**

Run: `pytest -q`

Expected: all tests pass.

### Task 4: Publish the implementation safely

**Files:**
- Modify only files from Tasks 1 through 3.

- [ ] **Step 1: Run static checks**

Run: `python -m compileall -q src tests && git diff --check && pytest -q`

Expected: exit status 0.

- [ ] **Step 2: Review the exact diff**

Run: `git diff --stat && git diff -- .github/workflows/changeguard-full.yml action.yml src/changeguard/github_demo.py src/changeguard/triage.py`

Expected: no unrelated files, no upstream write command, no pull-request checkout in the trusted workflow.

- [ ] **Step 3: Commit and push**

Commit the implementation on `codex/github-demo-prs`, push it, open a pull request to `main`, wait for the CPU check, then merge it. Push the previously approved product and design documentation with the same reviewed change if it is not already on `origin/main`.

### Task 5: Freeze five research records before inference

**Files:**
- Create: `docs/demo-cases.json`

- [ ] **Step 1: Read candidates from the frozen FT06 bundle**

Use `data/train.jsonl.zst` for four candidates and one frozen evaluation split for the fifth. Filter before scoring for distinct repositories, at least two PASS and two REVIEW labels, prompt length at most 8,192, small touched-file count, permissive public source, and reconstructable base revision.

- [ ] **Step 2: Resolve immutable upstream provenance**

For every selected record, resolve repository, instance ID, upstream issue URL, source revision or base commit, patch SHA-256, record ID, source dataset, split exposure, label, and license. Fetch only the original touched files at the base commit.

- [ ] **Step 3: Verify exact reconstruction**

Apply the frozen patch with `git apply --check`, apply it, regenerate the diff against the base commit, normalize only Git transport metadata, and assert its SHA-256 matches the frozen patch. Reject the case before inference if it cannot match.

- [ ] **Step 4: Freeze the case manifest**

Write `docs/demo-cases.json` with the five selected records and selection policy. Run `python -m json.tool docs/demo-cases.json >/dev/null` and verify that no model score is present.

### Task 6: Create five linked issues and open demo pull requests

**Files:**
- No new main-branch source files beyond `docs/demo-cases.json`.
- Create remote branches: `demo/base-<case>`, `demo/<case>`.

- [ ] **Step 1: Create local ChangeGuard issues**

Create one issue per case using the exact frozen source issue title and body. Append no provenance to the issue text because the collector must reproduce the research input. Record the resulting local issue number in the case manifest.

- [ ] **Step 2: Push case-specific base and head branches**

Start each base branch from current `main`, add the exact pre-patch files in one preparation commit, then create its head branch and apply the frozen patch. Do not merge either branch.

- [ ] **Step 3: Open five `[Demo]` pull requests**

Target each case-specific base branch. The body starts with `Fixes #<local issue>` and then presents a compact provenance table containing source repository, original issue, dataset, FT06 exposure, record ID, patch hash, and execution-grounded label. State that the example was selected before demo inference.

- [ ] **Step 4: Verify automatic workflows started**

Confirm the read-only CPU workflow and trusted FT06 workflow both start for all five pull requests. Do not add comments to upstream issues or pull requests.

### Task 7: Wait for model results and audit the portfolio surface

**Files:**
- Update: `docs/demo-cases.json` only if run URLs and immutable result metadata are intentionally recorded on `main` through a reviewed change.

- [ ] **Step 1: Monitor all ten workflow runs**

Wait until each CPU run and FT06 run completes. Inspect failed job logs before retrying. Do not change selected examples based on their scores.

- [ ] **Step 2: Verify report comments**

Each pull request must contain exactly one `<!-- changeguard-risk-triage-v1 -->` comment authored by `github-actions[bot]`. Confirm the report contains no emoji, no em dash, no safety approval language, and includes a completed model signal or a precise failure status.

- [ ] **Step 3: Verify final repository state**

Run: `gh pr list --repo tkim602/ChangeGuard --state open --search '[Demo] in:title'`

Expected: five open demo pull requests.

- [ ] **Step 4: Report the result**

Provide the five pull request URLs, their exposure classes, expected labels, FT06 signals, workflow URLs, and any failures. Explicitly distinguish demonstrations on training-exposed examples from evaluation evidence.
