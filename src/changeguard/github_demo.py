from __future__ import annotations

import argparse
import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

from changeguard.triage import analyze_patch, build_result, render_markdown


MARKER = "<!-- changeguard-risk-triage-v1 -->"


class GitHubClient:
    def __init__(self, token: str, base_url: str = "https://api.github.com", timeout: float = 30, max_bytes: int = 20_000_000):
        if not token:
            raise ValueError("GitHub token is required")
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_bytes = max_bytes

    def request(self, method: str, path: str, *, accept: str = "application/vnd.github+json", value: dict | None = None):
        body = json.dumps(value).encode() if value is not None else None
        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            method=method,
            headers={
                "Accept": accept,
                "Authorization": f"Bearer {self.token}",
                "User-Agent": "changeguard-risk-triage-v1",
                "X-GitHub-Api-Version": "2022-11-28",
                **({"Content-Type": "application/json"} if body is not None else {}),
            },
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            length = response.headers.get("Content-Length")
            if length and int(length) > self.max_bytes:
                raise ValueError("GitHub response exceeds size cap")
            data = response.read(self.max_bytes + 1)
            if len(data) > self.max_bytes:
                raise ValueError("GitHub response exceeds size cap")
            if accept.endswith("diff") or response.headers.get_content_type() == "text/plain":
                return data.decode()
            return json.loads(data)

    def get(self, path: str, *, accept: str = "application/vnd.github+json"):
        return self.request("GET", path, accept=accept)

    def post(self, path: str, value: dict):
        return self.request("POST", path, value=value)

    def patch(self, path: str, value: dict):
        return self.request("PATCH", path, value=value)


def issue_input(pr: dict, issue_lookup: Callable[[int], dict]) -> tuple[str, str]:
    body = pr.get("body") or ""
    numbers = {int(value) for value in re.findall(r"(?i)\b(?:fix(?:e[sd])?|close[sd]?|resolve[sd]?)\s+#(\d+)", body)}
    if len(numbers) == 1:
        number = numbers.pop()
        issue = issue_lookup(number)
        title, issue_body = issue.get("title") or "", issue.get("body") or ""
        if title or issue_body:
            return f"{title}\n\n{issue_body}".strip(), f"linked_issue_{number}"
    value = f"{pr.get('title') or ''}\n\n{body}".strip()
    return value, "PR_DESCRIPTION_FALLBACK" if value else "INSUFFICIENT_CONTEXT"


def _python_paths(diff: str) -> list[str]:
    paths = []
    for line in diff.splitlines():
        if line.startswith(("--- a/", "+++ b/")):
            path = line[6:]
            if path.endswith(".py"):
                paths.append(path)
    return sorted(set(paths))


def _file_content(client: GitHubClient, repo: str, path: str, ref: str, max_file_bytes: int = 500_000) -> str | None:
    encoded_path = urllib.parse.quote(path, safe="/")
    encoded_ref = urllib.parse.quote(ref, safe="")
    try:
        result = client.get(f"/repos/{repo}/contents/{encoded_path}?ref={encoded_ref}")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    if result.get("encoding") != "base64" or not isinstance(result.get("content"), str):
        return None
    data = base64.b64decode(result["content"])
    if len(data) > max_file_bytes:
        return None
    try:
        return data.decode()
    except UnicodeDecodeError:
        return None


def collect_pr(client: GitHubClient, repo: str, number: int) -> dict:
    pr = client.get(f"/repos/{repo}/pulls/{number}")
    diff = client.get(f"/repos/{repo}/pulls/{number}", accept="application/vnd.github.v3.diff")
    base_sha, head_sha = pr["base"]["sha"], pr["head"]["sha"]
    issue_text, issue_source = issue_input(pr, lambda issue_number: client.get(f"/repos/{repo}/issues/{issue_number}"))
    before_after = {}
    for path in _python_paths(diff):
        before_after[path] = [
            _file_content(client, repo, path, base_sha),
            _file_content(client, repo, path, head_sha),
        ]
    return {
        "repository": repo,
        "pull_request": number,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "issue_text": issue_text,
        "issue_source": issue_source,
        "context_status": "LINKED_ISSUE" if issue_source.startswith("linked_issue_") else issue_source,
        "patch": diff,
        "before_after": before_after,
    }


def upsert_comment(client: GitHubClient, repo: str, number: int, body: str) -> dict:
    if MARKER not in body:
        raise ValueError("ChangeGuard comment marker is missing")
    page = 1
    while True:
        suffix = "" if page == 1 else f"&page={page}"
        comments = client.get(f"/repos/{repo}/issues/{number}/comments?per_page=100{suffix}")
        existing = next((comment for comment in comments if MARKER in (comment.get("body") or "")), None)
        if existing:
            return client.patch(f"/repos/{repo}/issues/comments/{existing['id']}", {"body": body})
        if len(comments) < 100:
            break
        page += 1
    return client.post(f"/repos/{repo}/issues/{number}/comments", {"body": body})


def _cli() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    collect = commands.add_parser("collect")
    collect.add_argument("--repo", required=True)
    collect.add_argument("--pr", type=int, required=True)
    collect.add_argument("--output", type=Path, required=True)
    analyze = commands.add_parser("analyze")
    analyze.add_argument("--input", type=Path, required=True)
    analyze.add_argument("--model", type=Path)
    analyze.add_argument("--output", type=Path, required=True)
    analyze.add_argument("--markdown", type=Path, required=True)
    comment = commands.add_parser("comment")
    comment.add_argument("--repo", required=True)
    comment.add_argument("--pr", type=int, required=True)
    comment.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "collect":
        client = GitHubClient(os.environ.get("GITHUB_TOKEN", ""))
        args.output.write_text(json.dumps(collect_pr(client, args.repo, args.pr), indent=2, sort_keys=True) + "\n")
    elif args.command == "analyze":
        value = json.loads(args.input.read_text())
        pairs = {path: tuple(contents) for path, contents in value.get("before_after", {}).items()}
        analysis = analyze_patch(value["patch"], profile="github-context", before_after=pairs)
        model = json.loads(args.model.read_text()) if args.model and args.model.is_file() else None
        result = build_result(analysis, model=model, fingerprints={"base_sha": value["base_sha"], "head_sha": value["head_sha"]})
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        args.markdown.write_text(render_markdown(result))
    else:
        client = GitHubClient(os.environ.get("GITHUB_TOKEN", ""))
        upsert_comment(client, args.repo, args.pr, args.markdown.read_text())


if __name__ == "__main__":
    _cli()
