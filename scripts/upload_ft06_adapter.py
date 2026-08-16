#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CALIBRATION_PREDICTIONS_SHA256 = "59f969b9ed993da2d71372adc6f48cfd0d7ecfc8e8b862567ad8b92ef4835f75"


def load_contract():
    path = ROOT / "deployment/changeguard_ft06.py"
    spec = importlib.util.spec_from_file_location("changeguard_ft06_modal", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_calibration(path: Path) -> list[float]:
    observed = hashlib.sha256(path.read_bytes()).hexdigest()
    if observed != CALIBRATION_PREDICTIONS_SHA256:
        raise ValueError(f"calibration prediction hash mismatch: {observed}")
    values = sorted(1 - float(json.loads(line)["safe_score"]) for line in path.read_text().splitlines() if line.strip())
    if len(values) != 4003:
        raise ValueError(f"calibration row count mismatch: {len(values)}")
    return values


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--calibration-predictions", type=Path, required=True)
    parser.add_argument("--volume", default="changeguard-ft06-models")
    args = parser.parse_args()
    contract = load_contract()
    hashes = contract.validate_adapter(args.adapter)
    calibration = load_calibration(args.calibration_predictions)
    import modal

    volume = modal.Volume.from_name(args.volume, create_if_missing=True)
    with tempfile.TemporaryDirectory(prefix="changeguard-ft06-upload-") as directory:
        calibration_path = Path(directory) / "calibration_unsafe.json"
        calibration_path.write_text(json.dumps(calibration, separators=(",", ":")) + "\n")
        calibration_sha = hashlib.sha256(calibration_path.read_bytes()).hexdigest()
        if calibration_sha != contract.CALIBRATION_SHA256:
            raise ValueError(f"calibration artifact hash mismatch: {calibration_sha}")
        with volume.batch_upload() as upload:
            upload.put_directory(args.adapter, "ft06/adapter")
            upload.put_file(calibration_path, "ft06/calibration_unsafe.json")
    print(json.dumps({"adapter": hashes, "calibration_rows": len(calibration), "calibration_sha256": calibration_sha, "volume": args.volume}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
