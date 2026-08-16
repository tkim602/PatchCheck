from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping

import ast
import json
import re


SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}
RULES_PATH = Path(__file__).parents[2] / "configs/triage/rules_v1.json"


@dataclass(frozen=True)
class Evidence:
    rule_id: str
    severity: str
    confidence: str
    file: str
    line: int | None
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Analysis:
    version: str
    profile: str
    status: str
    findings: tuple[Evidence, ...]
    change_types: tuple[str, ...]
    skipped_files: tuple[tuple[str, str], ...]

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "profile": self.profile,
            "status": self.status,
            "findings": [item.to_dict() for item in self.findings],
            "change_types": list(self.change_types),
            "skipped_files": [list(item) for item in self.skipped_files],
        }


@dataclass(frozen=True)
class _ChangedLine:
    kind: str
    number: int
    text: str


@dataclass
class _DiffFile:
    path: str
    lines: list[_ChangedLine]
    binary: bool = False


def load_rule_config(path: Path = RULES_PATH) -> dict:
    config = json.loads(path.read_text())
    rules = config.get("rules", [])
    ids = [rule.get("id") for rule in rules]
    if not config.get("version") or len(ids) != len(set(ids)):
        raise ValueError("invalid or duplicate rule IDs")
    if any(rule.get("severity") not in SEVERITY_RANK for rule in rules):
        raise ValueError("unknown rule severity")
    return config


RULE_CONFIG = load_rule_config()
RULES = {rule["id"]: rule for rule in RULE_CONFIG["rules"]}


def _evidence(rule_id: str, path: str, line: int | None, message: str, confidence: str = "high") -> Evidence:
    return Evidence(rule_id, RULES[rule_id]["severity"], confidence, path, line, message)


def _parse_diff(patch: str) -> list[_DiffFile]:
    files: list[_DiffFile] = []
    current: _DiffFile | None = None
    old_line = new_line = 0
    for raw in patch.replace("\r\n", "\n").splitlines():
        if raw.startswith("diff --git "):
            match = re.match(r"diff --git a/(.+) b/(.+)$", raw)
            path = match.group(2) if match else raw.rsplit(" ", 1)[-1].removeprefix("b/")
            current = _DiffFile(path=path, lines=[])
            files.append(current)
            continue
        if current is None:
            continue
        if raw.startswith("Binary files ") or raw.startswith("GIT binary patch"):
            current.binary = True
            continue
        if raw.startswith("+++ b/"):
            current.path = raw[6:]
            continue
        if raw.startswith("@@ "):
            match = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", raw)
            if match:
                old_line, new_line = map(int, match.groups())
            continue
        if raw.startswith("+") and not raw.startswith("+++"):
            current.lines.append(_ChangedLine("add", new_line, raw[1:]))
            new_line += 1
        elif raw.startswith("-") and not raw.startswith("---"):
            current.lines.append(_ChangedLine("remove", old_line, raw[1:]))
            old_line += 1
        elif raw.startswith(" "):
            old_line += 1
            new_line += 1
    return files


def _is_test(path: str) -> bool:
    lower = path.lower()
    return lower.startswith("tests/") or "/tests/" in lower or lower.endswith("_test.py") or Path(lower).name.startswith("test_")


def _is_docs(path: str) -> bool:
    lower = path.lower()
    return lower.startswith("docs/") or lower.endswith((".md", ".rst", ".txt"))


def _is_dependency(path: str) -> bool:
    name = Path(path).name.lower()
    return name.startswith("requirements") or name in {"pyproject.toml", "poetry.lock", "pdm.lock", "package.json", "package-lock.json", "yarn.lock", "uv.lock"}


def _is_config(path: str) -> bool:
    lower = path.lower()
    return lower.startswith(("config/", ".github/")) or lower.endswith((".yaml", ".yml", ".toml", ".ini", ".cfg"))


def _function_signatures(lines: list[_ChangedLine], kind: str) -> dict[str, tuple[str, int]]:
    output = {}
    pattern = re.compile(r"\s*(?:async\s+)?def\s+([A-Za-z_]\w*)\s*(\(.*\)(?:\s*->\s*[^:]+)?):\s*$")
    for line in lines:
        if line.kind == kind and (match := pattern.match(line.text)):
            output[match.group(1)] = (re.sub(r"\s+", "", match.group(2)), line.number)
    return output


def _portable_file_findings(file: _DiffFile, all_paths: set[str]) -> tuple[list[Evidence], set[str]]:
    path = file.path
    lower = path.lower()
    added = [line for line in file.lines if line.kind == "add"]
    removed = [line for line in file.lines if line.kind == "remove"]
    findings: list[Evidence] = []
    types: set[str] = set()
    is_test = _is_test(path)
    is_docs = _is_docs(path)
    if is_test:
        types.add("test")
    elif is_docs:
        types.add("documentation")
    else:
        types.add("production")

    if re.search(r"(?:^|/)(?:auth|authentication|authorization|permissions?|security)(?:[_.-]|/|$)", lower):
        findings.append(_evidence("CG001", path, None, "authentication or authorization path modified"))
        types.add("authentication")
    if "migration" in lower:
        findings.append(_evidence("CG004", path, None, "database migration modified"))
        types.add("migration")
    if _is_dependency(path):
        findings.append(_evidence("CG003", path, None, "dependency manifest or lockfile modified"))
        types.add("dependency")
    if _is_config(path):
        findings.append(_evidence("CG013", path, None, "configuration modified"))
        types.add("configuration")
    if lower.startswith(".github/workflows/"):
        findings.append(_evidence("CG014", path, None, "GitHub workflow modified"))
        types.add("workflow")

    old_defs = _function_signatures(file.lines, "remove")
    new_defs = _function_signatures(file.lines, "add")
    for name in sorted(old_defs.keys() & new_defs.keys()):
        if not name.startswith("_") and old_defs[name][0] != new_defs[name][0]:
            findings.append(_evidence("CG006", path, new_defs[name][1], f"public function signature changed: {name}"))
            types.add("api_contract")

    old_imports = {line.text.strip() for line in removed if re.match(r"\s*(?:from\s+\S+\s+)?import\s+", line.text)}
    new_imports = {line.text.strip() for line in added if re.match(r"\s*(?:from\s+\S+\s+)?import\s+", line.text)}
    if old_imports != new_imports and (old_imports or new_imports):
        line = next((item.number for item in added if item.text.strip() in new_imports), None)
        findings.append(_evidence("CG017", path, line, "imports added or removed"))

    for line in added:
        text = line.text
        if re.search(r"\b(?:eval|exec)\s*\(", text):
            findings.append(_evidence("CG007", path, line.number, "dynamic code execution added"))
        if re.search(r"\bsubprocess\.(?:run|Popen|call|check_output|check_call)\s*\(.*\bshell\s*=\s*True", text):
            findings.append(_evidence("CG008", path, line.number, "shell-enabled subprocess added"))
        if re.search(r"(?i)\b(?:api[_-]?key|secret|password|access[_-]?token)\b\s*=\s*['\"][^'\"]{8,}['\"]", text):
            findings.append(_evidence("CG009", path, line.number, "secret-like literal added", "medium"))
        if re.match(r"\s*except\s*(?:Exception|BaseException)?\s*:", text):
            findings.append(_evidence("CG011", path, line.number, "broad exception handler added"))
        if re.search(r"(?:@pytest\.mark\.(?:skip|xfail)|\bpytest\.skip\s*\(|\bunittest\.skip)", text):
            findings.append(_evidence("CG012", path, line.number, "test disabling marker added"))
        if re.search(r"(?:chmod\s*\([^,]+,\s*0?777|\bpermissions?\s*:\s*(?:write|write-all))", text, re.I):
            rule = "CG002" if lower.startswith(".github/workflows/") else "CG019"
            findings.append(_evidence(rule, path, line.number, "permission expansion added"))
    for line in removed:
        if re.match(r"\s*(?:assert\b|raise\s+\w*Error\b)", line.text):
            line_number = next((new_defs[name][1] for name in old_defs.keys() & new_defs.keys()), line.number)
            findings.append(_evidence("CG010", path, line_number, "validation or assertion removed"))
        if re.match(r"\s*except\b", line.text):
            findings.append(_evidence("CG018", path, line.number, "exception handler removed"))

    if len(added) + len(removed) >= 500:
        findings.append(_evidence("CG020", path, None, "large diff contains at least 500 changed lines"))

    if not is_test and not is_docs and path.endswith(".py") and not any(_is_test(item) for item in all_paths):
        findings.append(_evidence("CG005", path, None, "production Python changed without test-file changes"))
    return findings, types


def _annotation_dump(node: ast.AST | None) -> str:
    return ast.dump(node, include_attributes=False) if node is not None else ""


def _signature_dump(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    return ast.dump(node.args, include_attributes=False) + "->" + _annotation_dump(node.returns)


def _handler_name(node: ast.ExceptHandler) -> str:
    if node.type is None:
        return "bare"
    if isinstance(node.type, ast.Name):
        return node.type.id
    return _annotation_dump(node.type)


def _github_context_findings(path: str, before: str | None, after: str | None, max_bytes: int = 500_000) -> tuple[list[Evidence], str | None]:
    if before is None or after is None:
        return [], "missing before/after file"
    if len(before.encode()) > max_bytes or len(after.encode()) > max_bytes:
        return [], "file exceeds AST byte cap"
    try:
        old_tree = ast.parse(before)
    except SyntaxError:
        return [], "unparsable before file"
    try:
        new_tree = ast.parse(after)
    except SyntaxError:
        return [], "unparsable after file"

    findings: list[Evidence] = []
    old_public = {
        node.name: node
        for node in old_tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not node.name.startswith("_")
    }
    new_public = {
        node.name: node
        for node in new_tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not node.name.startswith("_")
    }
    for name in sorted(old_public.keys() - new_public.keys()):
        findings.append(_evidence("CG006", path, getattr(old_public[name], "lineno", None), f"public symbol removed: {name}"))
    for name in sorted(old_public.keys() & new_public.keys()):
        old_node, new_node = old_public[name], new_public[name]
        if isinstance(old_node, (ast.FunctionDef, ast.AsyncFunctionDef)) and isinstance(new_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if _signature_dump(old_node) != _signature_dump(new_node):
                findings.append(_evidence("CG006", path, new_node.lineno, f"public function signature changed: {name}"))

    old_asserts = sum(isinstance(node, ast.Assert) for node in ast.walk(old_tree))
    new_asserts = sum(isinstance(node, ast.Assert) for node in ast.walk(new_tree))
    if new_asserts < old_asserts:
        findings.append(_evidence("CG010", path, None, f"{old_asserts - new_asserts} assertion(s) removed"))

    old_handlers = [_handler_name(node) for node in ast.walk(old_tree) if isinstance(node, ast.ExceptHandler)]
    new_handler_nodes = [node for node in ast.walk(new_tree) if isinstance(node, ast.ExceptHandler)]
    new_handlers = [_handler_name(node) for node in new_handler_nodes]
    if len(new_handlers) < len(old_handlers) or any(name not in new_handlers for name in old_handlers):
        findings.append(_evidence("CG018", path, None, "exception handling narrowed or removed"))
    for node, name in zip(new_handler_nodes, new_handlers, strict=True):
        if name in {"bare", "Exception", "BaseException"} and name not in old_handlers:
            findings.append(_evidence("CG011", path, node.lineno, f"broad exception handler added: {name}"))
    return findings, None


def analyze_patch(
    patch: str,
    profile: str = "portable-core",
    before_after: Mapping[str, tuple[str | None, str | None]] | None = None,
) -> Analysis:
    if profile not in {"portable-core", "github-context"}:
        raise ValueError(f"unknown profile: {profile}")
    files = _parse_diff(patch)
    if not files:
        return Analysis(RULE_CONFIG["version"], profile, "unsupported", (), (), (("<patch>", "no unified diff files"),))
    findings: list[Evidence] = []
    change_types: set[str] = set()
    skipped: list[tuple[str, str]] = []
    paths = {file.path for file in files}
    for file in files:
        if file.binary:
            skipped.append((file.path, "binary"))
            continue
        file_findings, file_types = _portable_file_findings(file, paths)
        findings.extend(file_findings)
        change_types.update(file_types)
        if profile == "github-context" and file.path.endswith(".py"):
            pair = (before_after or {}).get(file.path, (None, None))
            context_findings, reason = _github_context_findings(file.path, *pair)
            findings.extend(context_findings)
            if reason:
                skipped.append((file.path, reason))
    non_skipped = [file for file in files if not file.binary]
    if non_skipped and all(_is_test(file.path) for file in non_skipped):
        findings.append(_evidence("CG016", non_skipped[0].path, None, "test-only change"))
    if non_skipped and all(_is_docs(file.path) for file in non_skipped):
        findings.append(_evidence("CG015", non_skipped[0].path, None, "documentation-only change"))
    unique = {(item.rule_id, item.file, item.line, item.message): item for item in findings}
    ordered = tuple(sorted(unique.values(), key=lambda item: (item.file, -1 if item.line is None else item.line, item.rule_id)))
    status = "partial" if skipped else "complete"
    return Analysis(RULE_CONFIG["version"], profile, status, ordered, tuple(sorted(change_types)), tuple(sorted(skipped)))


def _signal(percentile: float) -> str:
    if not 0.0 <= percentile <= 1.0:
        raise ValueError("risk percentile must be between zero and one")
    if percentile < 0.5:
        return "LOWER"
    if percentile < 0.8:
        return "ELEVATED"
    return "HIGH"


def build_result(
    analysis: Analysis,
    model: Mapping[str, object] | None = None,
    fingerprints: Mapping[str, str] | None = None,
) -> dict:
    model_result = dict(model or {"status": "MODEL_NOT_RUN: NOT_REQUESTED"})
    if model_result.get("status") == "complete":
        if "risk_percentile" not in model_result:
            raise ValueError("complete model result requires risk_percentile")
        model_result["signal"] = _signal(float(model_result["risk_percentile"]))
    return {
        "schema_version": "changeguard-risk-triage-v1",
        "model": model_result,
        "deterministic": {
            "status": analysis.status,
            "profile": analysis.profile,
            "change_types": list(analysis.change_types),
            "findings": [item.to_dict() for item in analysis.findings],
            "skipped_files": [list(item) for item in analysis.skipped_files],
        },
        "fingerprints": dict(sorted((fingerprints or {}).items())),
        "disclaimer": "Review-priority signal only; not a safety approval.",
    }


def _markdown(value: object) -> str:
    return str(value).replace("\\", "\\\\").replace("`", "\\`").replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;")


def render_markdown(result: Mapping[str, object], max_findings: int = 12) -> str:
    model = dict(result["model"])
    deterministic = dict(result["deterministic"])
    lines = ["<!-- changeguard-risk-triage-v1 -->", "## ChangeGuard Risk Triage", ""]
    if model.get("status") == "complete":
        lines.extend([
            f"Model signal: **{_markdown(model['signal'])}**",
            f"Model risk percentile: **{100 * float(model['risk_percentile']):.1f}**",
        ])
    else:
        lines.append(f"Model status: **{_markdown(model.get('status', 'MODEL_NOT_RUN'))}**")
    lines.extend(["", "### Code-change flags"])
    findings = list(deterministic.get("findings", []))
    if findings:
        for item in findings[:max_findings]:
            location = item["file"] + (f":{item['line']}" if item.get("line") is not None else "")
            lines.append(f"- `{_markdown(item['rule_id'])}` **{_markdown(item['severity'])}** — {_markdown(item['message'])} (`{_markdown(location)}`)")
        if len(findings) > max_findings:
            lines.append(f"- … {len(findings) - max_findings} additional finding(s) are in the JSON artifact.")
    else:
        lines.append("- No portable deterministic finding. This is not evidence that the patch is safe.")
    skipped = list(deterministic.get("skipped_files", []))
    if skipped:
        lines.extend(["", "Skipped analysis:"])
        lines.extend(f"- `{_markdown(path)}` — {_markdown(reason)}" for path, reason in skipped)
    fingerprints = dict(result.get("fingerprints", {}))
    if fingerprints:
        lines.extend(["", "<details><summary>Fingerprints</summary>", ""])
        lines.extend(f"- `{_markdown(key)}`: `{_markdown(value)}`" for key, value in sorted(fingerprints.items()))
        lines.extend(["", "</details>"])
    lines.extend(["", f"_{_markdown(result['disclaimer'])}_", ""])
    return "\n".join(lines)
