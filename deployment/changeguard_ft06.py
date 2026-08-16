from __future__ import annotations

"""Scale-to-zero Modal entrypoint for the frozen FT06 adapter."""

import hashlib
import json
import math
from bisect import bisect_right
from pathlib import Path


MODEL_ID = "Qwen/Qwen2.5-Coder-7B-Instruct"
MODEL_REVISION = "c03e6d358207e414f1eca0bb1891e29f1db0e242"
ADAPTER_SHA256 = "1120ffebdda57294069ffb437b993fc3c97518056f6fe55ab918154b20f888a8"
ADAPTER_CONFIG_SHA256 = "c33b86676674ec37c7092da84f440e93d4156ca2ab6f1ee2768531756351b9db"
PROMPT_SHA256 = "c6bfbe7eccfa923e514f655525df63028bda13ed5a51d97732b4cee07bfb356c"
MODEL_ROOT = Path("/models/ft06")
ADAPTER_DIR = MODEL_ROOT / "adapter"
CALIBRATION_PATH = MODEL_ROOT / "calibration_unsafe.json"
CALIBRATION_SHA256 = "86cbf0dec43e6ef878e603ebb5d819e1b598f99a4c0d8fb0312906a49eaa70a3"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_adapter(path: Path) -> dict[str, str]:
    observed = {
        "adapter_model.safetensors": _sha256(path / "adapter_model.safetensors"),
        "adapter_config.json": _sha256(path / "adapter_config.json"),
    }
    expected = {
        "adapter_model.safetensors": ADAPTER_SHA256,
        "adapter_config.json": ADAPTER_CONFIG_SHA256,
    }
    if observed != expected:
        raise ValueError(f"adapter hash mismatch: observed={observed} expected={expected}")
    return observed


def messages(row: dict) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": "You are a software patch verifier."},
        {"role": "user", "content": f"[ISSUE]\n{row['issue_text']}\n\n[PATCH]\n{row['patch']}\n\nDetermine whether the patch correctly resolves the issue without introducing an incorrect solution.\nAnswer with exactly one label."},
    ]


def token_status(tokens: int) -> str:
    return "READY" if tokens <= 8192 else "MODEL_NOT_RUN: OVER_8192"


def input_status(row: dict, tokens: int) -> str:
    if not str(row.get("issue_text", "")).strip():
        return "MODEL_NOT_RUN: INSUFFICIENT_CONTEXT"
    return token_status(tokens)


def _risk_percentile(value: float, calibration: list[float]) -> float:
    return bisect_right(calibration, value) / len(calibration)


try:
    import modal
except ModuleNotFoundError:  # Local contract tests do not require Modal.
    modal = None


if modal is not None:
    REQUIREMENTS = [
        "torch==2.13.0",
        "transformers==5.15.0",
        "peft==0.20.0",
        "accelerate==1.14.0",
        "bitsandbytes==0.50.0",
        "huggingface-hub==1.27.0",
    ]
    image = modal.Image.debian_slim(python_version="3.12").pip_install(*REQUIREMENTS)
    volume = modal.Volume.from_name("changeguard-ft06-models", create_if_missing=False)
    app = modal.App("changeguard-ft06-github", image=image)

    @app.cls(gpu="L40S", volumes={"/models": volume}, timeout=900)
    class FT06:
        @modal.enter()
        def load(self) -> None:
            import torch
            from peft import PeftModel
            from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

            validate_adapter(ADAPTER_DIR)
            if _sha256(CALIBRATION_PATH) != CALIBRATION_SHA256:
                raise ValueError("calibration artifact hash mismatch")
            self.tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, revision=MODEL_REVISION, use_fast=True, cache_dir="/models/hf")
            self.tokenizer.padding_side = "left"
            self.tokenizer.pad_token = self.tokenizer.eos_token
            quant = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
                bnb_4bit_compute_dtype=torch.bfloat16,
            )
            base = AutoModelForCausalLM.from_pretrained(
                MODEL_ID,
                revision=MODEL_REVISION,
                quantization_config=quant,
                dtype=torch.bfloat16,
                device_map="auto",
                attn_implementation="sdpa",
                cache_dir="/models/hf",
            )
            self.model = PeftModel.from_pretrained(base, ADAPTER_DIR)
            self.model.eval()
            self.calibration = sorted(json.loads(CALIBRATION_PATH.read_text()))

        def _prompt_ids(self, row: dict) -> list[int]:
            rendered = self.tokenizer.apply_chat_template(messages(row), tokenize=False, add_generation_prompt=True)
            return self.tokenizer(rendered, add_special_tokens=False).input_ids

        def _sequence_score(self, prompt: list[int], completion: list[int]) -> float:
            import torch

            ids = torch.tensor([prompt + completion], device=self.model.get_input_embeddings().weight.device)
            mask = torch.ones_like(ids)
            with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
                logits = self.model(input_ids=ids, attention_mask=mask).logits.log_softmax(-1)
            return sum(float(logits[0, len(prompt) + index - 1, token]) for index, token in enumerate(completion))

        @modal.method()
        def score(self, row: dict) -> dict:
            prompt = self._prompt_ids(row)
            safe = self.tokenizer(" PASS", add_special_tokens=False).input_ids
            review = self.tokenizer(" REVIEW", add_special_tokens=False).input_ids
            tokens = max(len(prompt) + len(safe), len(prompt) + len(review))
            status = input_status(row, tokens)
            if status != "READY":
                return {"status": status, "input_tokens": tokens}
            safe_logp = self._sequence_score(prompt, safe)
            review_logp = self._sequence_score(prompt, review)
            raw_safe = safe_logp - review_logp
            safe_score = 1 / (1 + math.exp(-max(-50, min(50, raw_safe))))
            unsafe_score = 1 - safe_score
            return {
                "status": "complete",
                "input_tokens": tokens,
                "raw_safe_score": raw_safe,
                "safe_score": safe_score,
                "risk_percentile": _risk_percentile(unsafe_score, self.calibration),
                "model_id": MODEL_ID,
                "model_revision": MODEL_REVISION,
                "adapter_sha256": ADAPTER_SHA256,
                "adapter_config_sha256": ADAPTER_CONFIG_SHA256,
                "prompt_sha256": PROMPT_SHA256,
                "calibration_sha256": CALIBRATION_SHA256,
                "input_sha256": hashlib.sha256((row["issue_text"] + "\0" + row["patch"]).encode()).hexdigest(),
            }

    @app.local_entrypoint()
    def main(input: str, output: str) -> None:
        row = json.loads(Path(input).read_text())
        result = FT06().score.remote(row)
        Path(output).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
