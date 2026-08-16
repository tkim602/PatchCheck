from __future__ import annotations

import json
import importlib.util
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class GitHubHandler(BaseHTTPRequestHandler):
    requests: list[tuple[str, str, str]] = []
    comment_body = "<!-- changeguard-risk-triage-v1 -->\nold"

    def log_message(self, *_args) -> None:
        pass

    def _send(self, value, content_type="application/json") -> None:
        body = value if isinstance(value, bytes) else json.dumps(value).encode()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        accept = self.headers.get("Accept", "")
        self.requests.append(("GET", self.path, accept))
        if self.path == "/repos/o/r/pulls/7" and "diff" in accept:
            self._send(b"diff --git a/src/auth.py b/src/auth.py\n--- a/src/auth.py\n+++ b/src/auth.py\n@@ -1 +1 @@\n-x=1\n+x=2\n", "text/plain")
        elif self.path == "/repos/o/r/pulls/7":
            self._send({"number": 7, "title": "fix", "body": "Fixes #5", "base": {"sha": "base"}, "head": {"sha": "head"}})
        elif self.path == "/repos/o/r/issues/5":
            self._send({"title": "real issue", "body": "expected behavior"})
        elif self.path.startswith("/repos/o/r/contents/src/auth.py?ref="):
            import base64

            value = "x=1\n" if self.path.endswith("base") else "x=2\n"
            self._send({"encoding": "base64", "content": base64.b64encode(value.encode()).decode()})
        elif self.path == "/repos/o/r/issues/7/comments?per_page=100":
            self._send([{"id": 9, "body": self.comment_body}])
        else:
            self.send_error(404)

    def do_PATCH(self) -> None:
        self.requests.append(("PATCH", self.path, self.headers.get("Accept", "")))
        length = int(self.headers["Content-Length"])
        self.__class__.comment_body = json.loads(self.rfile.read(length))["body"]
        self._send({"id": 9, "body": self.comment_body})


def test_collect_uses_fixed_shas_and_linked_issue() -> None:
    from changeguard.github_demo import GitHubClient, collect_pr

    server = ThreadingHTTPServer(("127.0.0.1", 0), GitHubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = GitHubClient("token", base_url=f"http://127.0.0.1:{server.server_port}")
        result = collect_pr(client, "o/r", 7)
    finally:
        server.shutdown()
        thread.join()
    assert result["base_sha"] == "base"
    assert result["head_sha"] == "head"
    assert result["issue_source"] == "linked_issue_5"
    assert result["context_status"] == "LINKED_ISSUE"
    assert result["issue_text"] == "real issue\nexpected behavior"
    assert result["before_after"]["src/auth.py"] == ["x=1\n", "x=2\n"]
    assert any(path.endswith("?ref=base") for _, path, _ in GitHubHandler.requests)
    assert any(path.endswith("?ref=head") for _, path, _ in GitHubHandler.requests)


def test_multiple_linked_issues_fall_back_to_pr_description() -> None:
    from changeguard.github_demo import issue_input

    pr = {"title": "title", "body": "Fixes #1 and closes #2"}
    assert issue_input(pr, lambda _number: {}) == ("title\n\nFixes #1 and closes #2", "PR_DESCRIPTION_FALLBACK")


def test_empty_pr_context_is_explicitly_insufficient() -> None:
    from changeguard.github_demo import issue_input

    assert issue_input({"title": "", "body": ""}, lambda _number: {}) == ("", "INSUFFICIENT_CONTEXT")


def test_python_paths_include_deleted_files() -> None:
    from changeguard.github_demo import _python_paths

    diff = "diff --git a/old.py b/old.py\n--- a/old.py\n+++ /dev/null\n"
    assert _python_paths(diff) == ["old.py"]


def test_comment_updates_existing_marker() -> None:
    from changeguard.github_demo import GitHubClient, upsert_comment

    GitHubHandler.requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), GitHubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = GitHubClient("token", base_url=f"http://127.0.0.1:{server.server_port}")
        upsert_comment(client, "o/r", 7, "<!-- changeguard-risk-triage-v1 -->\nnew")
    finally:
        server.shutdown()
        thread.join()
    assert ("PATCH", "/repos/o/r/issues/comments/9", "application/vnd.github+json") in GitHubHandler.requests
    assert GitHubHandler.comment_body.endswith("new")


def test_comment_lookup_paginates_before_creating() -> None:
    from changeguard.github_demo import upsert_comment

    class Client:
        def __init__(self):
            self.paths = []

        def get(self, path):
            self.paths.append(path)
            if "page=2" in path:
                return [{"id": 777, "body": "<!-- changeguard-risk-triage-v1 -->"}]
            return [{"id": i, "body": "ordinary"} for i in range(100)]

        def patch(self, path, value):
            return {"path": path, **value}

        def post(self, *_args):
            raise AssertionError("must not create a duplicate comment")

    client = Client()
    result = upsert_comment(client, "o/r", 7, "<!-- changeguard-risk-triage-v1 -->\nnew")
    assert result["path"].endswith("/777")
    assert client.paths[-1].endswith("&page=2")


def test_offline_analyze_cli_needs_no_github_token(tmp_path, monkeypatch) -> None:
    from changeguard import github_demo

    source = tmp_path / "input.json"
    output = tmp_path / "result.json"
    markdown = tmp_path / "report.md"
    source.write_text(json.dumps({
        "patch": "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-x=1\n+x=2\n",
        "before_after": {"a.py": ["x=1\n", "x=2\n"]},
        "base_sha": "base",
        "head_sha": "head",
    }))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(sys, "argv", ["changeguard", "analyze", "--input", str(source), "--output", str(output), "--markdown", str(markdown)])
    github_demo._cli()
    result = json.loads(output.read_text())
    assert "combined_priority" not in result
    assert "score" not in result["deterministic"]


def test_analyze_cli_can_render_frozen_model_result(tmp_path, monkeypatch) -> None:
    from changeguard import github_demo

    source = tmp_path / "input.json"
    model = tmp_path / "model.json"
    output = tmp_path / "result.json"
    markdown = tmp_path / "report.md"
    source.write_text(json.dumps({
        "patch": "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-x=1\n+x=2\n",
        "before_after": {},
        "base_sha": "base",
        "head_sha": "head",
    }))
    model.write_text(json.dumps({"status": "complete", "risk_percentile": 0.91}))
    monkeypatch.setattr(sys, "argv", [
        "changeguard", "analyze", "--input", str(source), "--model", str(model),
        "--output", str(output), "--markdown", str(markdown),
    ])
    github_demo._cli()
    assert json.loads(output.read_text())["model"]["signal"] == "HIGH"


def test_github_workflows_are_safe_and_pinned() -> None:
    from pathlib import Path

    root = Path(__file__).parents[1]
    automatic = (root / ".github/workflows/changeguard-evidence.yml").read_text()
    full = (root / ".github/workflows/changeguard-full.yml").read_text()
    assert "pull_request_target" not in automatic
    assert "pull_request_target:" in full
    assert "[opened, reopened, synchronize, labeled]" in full
    assert "actions/checkout@v7" in automatic + full
    assert "actions/setup-python@v7" in automatic + full
    assert "actions/upload-artifact@v7" in automatic + full
    assert "actions/checkout@v6" not in automatic + full
    assert "actions/setup-python@v5" not in automatic + full
    assert "actions/upload-artifact@v4" not in automatic + full
    assert "pull_request:" in automatic
    assert "name: ChangeGuard code-change flags" in automatic
    assert "pull-requests: read" in automatic
    assert "MODAL_TOKEN" not in automatic
    assert "workflow_dispatch:" in full
    assert "github.event.pull_request.user.login == 'tkim602'" in full
    assert "startsWith(github.event.pull_request.title, '[Demo]')" in full
    assert "github.event.label.name == 'changeguard-model'" in full
    assert "concurrency:" in full
    assert "github.event.pull_request.number || inputs.pull_request" in full
    assert "pull-requests: write" in full
    assert "MODAL_ENVIRONMENT: changeguard-demo" in full
    assert "timeout-minutes: 20" in full
    assert "modal==1.5.2" in full
    assert "jinja2==3.1.6" in full
    assert "deployment/changeguard_ft06.py" in full
    assert "if: steps.preflight.outcome == 'success'" in full
    assert "MODEL_NOT_RUN: MODAL_FAILED" in full
    assert "MODEL_NOT_RUN: PREFLIGHT_FAILED" in full
    assert "Require completed model result" in full
    assert "status == 'complete'" in full


def test_public_action_is_cpu_only_and_read_only() -> None:
    from pathlib import Path

    root = Path(__file__).parents[1]
    action = (root / "action.yml").read_text()
    example = (root / "docs/examples/changeguard.yml").read_text()
    assert "using: composite" in action
    assert "changeguard.github_demo collect" in action
    assert "changeguard.github_demo analyze" in action
    assert "MODAL_TOKEN" not in action + example
    assert "changeguard.github_demo comment" not in action + example
    assert "pull-requests: read" in example
    assert "issues: read" in example
    assert "uses: tkim602/ChangeGuard@main" in example


def load_modal_module():
    path = __import__("pathlib").Path(__file__).parents[1] / "deployment/changeguard_ft06.py"
    spec = importlib.util.spec_from_file_location("changeguard_ft06_modal", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_modal_prompt_is_exact_ft06_prompt() -> None:
    module = load_modal_module()
    messages = module.messages({"issue_text": "bug", "patch": "diff"})
    assert messages == [
        {"role": "system", "content": "You are a software patch verifier."},
        {"role": "user", "content": "[ISSUE]\nbug\n\n[PATCH]\ndiff\n\nDetermine whether the patch correctly resolves the issue without introducing an incorrect solution.\nAnswer with exactly one label."},
    ]


def test_modal_single_run_has_cost_timeout() -> None:
    source = (__import__("pathlib").Path(__file__).parents[1] / "deployment/changeguard_ft06.py").read_text()
    assert '@app.cls(gpu="L40S", volumes={"/models": volume}, timeout=900)' in source


def test_modal_rejects_empty_issue_context() -> None:
    module = load_modal_module()

    assert module.input_status({"issue_text": "  "}, 100) == "MODEL_NOT_RUN: INSUFFICIENT_CONTEXT"


def test_adapter_hash_gate_fails_before_modal_use(tmp_path) -> None:
    module = load_modal_module()
    adapter = tmp_path / "adapter"
    adapter.mkdir()
    (adapter / "adapter_model.safetensors").write_bytes(b"wrong")
    (adapter / "adapter_config.json").write_text("{}")
    try:
        module.validate_adapter(adapter)
    except ValueError as exc:
        assert "adapter hash mismatch" in str(exc)
    else:
        raise AssertionError("bad adapter was accepted")


def test_calibration_hash_gate_rejects_nonfrozen_predictions(tmp_path) -> None:
    from scripts.upload_ft06_adapter import load_calibration

    path = tmp_path / "calibration.jsonl"
    path.write_text('{"safe_score":0.5}\n')
    try:
        load_calibration(path)
    except ValueError as exc:
        assert "calibration prediction hash mismatch" in str(exc)
    else:
        raise AssertionError("nonfrozen calibration predictions were accepted")


def test_over_8192_status_is_explicit() -> None:
    module = load_modal_module()
    assert module.token_status(8192) == "READY"
    assert module.token_status(8193) == "MODEL_NOT_RUN: OVER_8192"
