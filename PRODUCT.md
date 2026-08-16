# Product

## Users

PatchCheck is built for software engineers and maintainers who want an additional review-priority signal for pull requests without executing untrusted PR code.

## Purpose

PatchCheck combines a frozen fine-tuned verifier with a separate deterministic code inspection. It is intended to help prioritize human review. It does not approve a patch, block a merge, or replace tests and code review.

## Design principles

1. Put provenance before interpretation.
2. Keep learned scores and deterministic findings separate.
3. State limitations in plain language.
4. Keep one stable report per pull request and update it in place.
5. Fail as unavailable or insufficient context, never as low risk.

## Writing style

Use concise engineering language. Avoid marketing claims, decorative status language, and wording that implies safety certification.
