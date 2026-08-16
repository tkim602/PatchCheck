# Product

## Register

brand

## Users

PatchCheck is presented to software engineers, maintainers, and hiring teams evaluating whether its author can fine-tune, validate, and deploy an AI-assisted developer tool. Maintainers use the repository to inspect how a pull request is collected, scored, and reported without running untrusted code.

## Product Purpose

PatchCheck demonstrates advisory pull-request risk triage with a frozen fine-tuned verifier and a separate deterministic code inspection. It helps prioritize human review. It does not approve a patch, block a merge, or replace tests and code review. Success means a visitor can inspect real pull requests, understand the model's exposure to each example, and trace every reported result to an immutable issue and patch.

## Brand Personality

Technical, restrained, candid. The voice should resemble a concise engineering review written by a careful maintainer.

## Anti-references

Avoid chatbot-style enthusiasm, emoji, decorative status badges, marketing claims, excessive formatting, generic praise, and language that implies safety certification. Do not hide training exposure or selection limits behind the headline result.

## Design Principles

1. Put provenance before interpretation.
2. Separate the learned signal from deterministic evidence.
3. State model exposure and limitations in plain language.
4. Keep one stable report per pull request and update it in place.
5. Fail as unavailable or insufficient context, never as low risk.

## Accessibility & Inclusion

Use semantic GitHub Markdown, descriptive headings, compact tables only for factual metadata, and status text that does not depend on color or icons. Keep reports readable with assistive technology and avoid emoji as the sole carrier of meaning.
