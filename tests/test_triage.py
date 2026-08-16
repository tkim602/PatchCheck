from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_rule_config_has_unique_known_severities() -> None:
    config = json.loads((Path(__file__).parents[1] / "configs/triage/rules_v1.json").read_text())
    assert config["version"] == "changeguard-deterministic-v1"
    assert config["max_prompt_evidence"] == 8
    assert config["max_prompt_chars"] == 1600
    assert len(config["rules"]) == len({rule["id"] for rule in config["rules"]})
    assert {rule["severity"] for rule in config["rules"]} <= {"low", "medium", "high", "critical"}


def test_public_demo_has_no_hybrid_scoring_helpers() -> None:
    import changeguard.triage as triage

    assert not hasattr(triage, "deterministic_score")
    assert not hasattr(triage, "empirical_percentile")
    assert not hasattr(triage, "candidate_combination")


PORTABLE_DIFF = """diff --git a/src/auth.py b/src/auth.py
index 1111111..2222222 100644
--- a/src/auth.py
+++ b/src/auth.py
@@ -1,5 +1,5 @@
-import os
+import subprocess
 # changeguard demo
-def validate(user: str) -> bool:
-    assert user
+def validate(user: str, admin: bool = False) -> bool:
+    subprocess.run(user, shell=True)
     return True
"""


def test_portable_diff_emits_exact_sorted_evidence() -> None:
    from changeguard.triage import analyze_patch

    analysis = analyze_patch(PORTABLE_DIFF)
    assert analysis.status == "complete"
    assert analysis.profile == "portable-core"
    assert analysis.change_types == ("api_contract", "authentication", "production")
    assert [(item.rule_id, item.file, item.line) for item in analysis.findings] == [
        ("CG001", "src/auth.py", None),
        ("CG005", "src/auth.py", None),
        ("CG017", "src/auth.py", 1),
        ("CG006", "src/auth.py", 3),
        ("CG010", "src/auth.py", 3),
        ("CG008", "src/auth.py", 4),
    ]


def test_binary_diff_is_explicitly_skipped() -> None:
    from changeguard.triage import analyze_patch

    patch = "diff --git a/logo.png b/logo.png\nBinary files a/logo.png and b/logo.png differ\n"
    analysis = analyze_patch(patch)
    assert analysis.status == "partial"
    assert analysis.findings == ()
    assert analysis.skipped_files == (("logo.png", "binary"),)


def test_malformed_diff_is_not_treated_as_safe() -> None:
    from changeguard.triage import analyze_patch

    analysis = analyze_patch("+eval(user_input)\n")
    assert analysis.status == "unsupported"
    assert analysis.findings == ()
    assert analysis.skipped_files == (("<patch>", "no unified diff files"),)


def test_github_context_compares_full_python_files() -> None:
    from changeguard.triage import analyze_patch

    patch = """diff --git a/src/api.py b/src/api.py
--- a/src/api.py
+++ b/src/api.py
@@ -1 +1 @@
-def public(value: int = 1) -> int:
+def public(value: str = 'x') -> str:
"""
    before = """def removed():\n    return 1\n\ndef public(value: int = 1) -> int:\n    assert value\n    try:\n        return value\n    except ValueError:\n        return 0\n"""
    after = """def public(value: str = 'x') -> str:\n    try:\n        return value\n    except Exception:\n        return ''\n"""
    portable = analyze_patch(patch, profile="portable-core", before_after={"src/api.py": (before, after)})
    context = analyze_patch(patch, profile="github-context", before_after={"src/api.py": (before, after)})
    assert {item.rule_id for item in portable.findings} == {"CG005", "CG006"}
    assert {item.rule_id for item in context.findings} == {"CG005", "CG006", "CG010", "CG011", "CG018"}


def test_github_context_records_unparsable_file_without_claim() -> None:
    from changeguard.triage import analyze_patch

    patch = "diff --git a/src/bad.py b/src/bad.py\n--- a/src/bad.py\n+++ b/src/bad.py\n@@ -1 +1 @@\n-x = 1\n+x = (\n"
    result = analyze_patch(patch, profile="github-context", before_after={"src/bad.py": ("x = 1\n", "x = (\n")})
    assert ("src/bad.py", "unparsable after file") in result.skipped_files
    assert not {"CG006", "CG010", "CG011", "CG018"} & {item.rule_id for item in result.findings}


def test_report_keeps_model_and_evidence_separate() -> None:
    from changeguard.triage import analyze_patch, build_result, render_markdown

    analysis = analyze_patch(PORTABLE_DIFF)
    result = build_result(
        analysis,
        model={"status": "complete", "risk_percentile": 0.72, "raw_safe_score": -0.3},
        fingerprints={"adapter_sha256": "abc", "input_sha256": "def"},
    )
    report = render_markdown(result)
    assert "combined_priority" not in result
    assert "score" not in result["deterministic"]
    assert result["model"]["signal"] == "ELEVATED"
    assert "Model signal: **ELEVATED**" in report
    assert "## ChangeGuard review" in report
    assert "### Code-change findings" in report
    assert "CG001" not in report
    assert "—" not in report
    assert not any(symbol in report for symbol in ("✅", "❌", "⚠️", "🚀", "✨"))
    assert "Combined priority" not in report
    assert "Review-priority signal only; not a safety approval." in report
    assert "<!-- changeguard-risk-triage-v1 -->" in report


@pytest.mark.parametrize("status", ["MODEL_NOT_RUN: OVER_8192", "MODEL_NOT_RUN: GPU_ERROR"])
def test_unavailable_model_never_becomes_lower_risk(status: str) -> None:
    from changeguard.triage import analyze_patch, build_result, render_markdown

    result = build_result(analyze_patch(PORTABLE_DIFF), model={"status": status})
    assert "signal" not in result["model"]
    assert "LOWER" not in render_markdown(result)
