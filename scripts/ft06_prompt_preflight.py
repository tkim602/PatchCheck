from __future__ import annotations

import argparse
import json
from pathlib import Path

from transformers import AutoTokenizer

from deployment.changeguard_ft06 import MODEL_ID, MODEL_REVISION, input_status, messages


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    row = json.loads(args.input.read_text())
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, revision=MODEL_REVISION, use_fast=True)
    rendered = tokenizer.apply_chat_template(messages(row), tokenize=False, add_generation_prompt=True)
    prompt = tokenizer(rendered, add_special_tokens=False).input_ids
    completion = max(
        len(tokenizer(" PASS", add_special_tokens=False).input_ids),
        len(tokenizer(" REVIEW", add_special_tokens=False).input_ids),
    )
    tokens = len(prompt) + completion
    status = input_status(row, tokens)
    result = {"status": status, "input_tokens": tokens}
    print(json.dumps(result, sort_keys=True))
    if args.output:
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    if status != "READY":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
