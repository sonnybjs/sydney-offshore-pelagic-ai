from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from model_audit_lib import AUDIT_ROOT, TARGET_SPECIES, ensure_audit_dirs, load_json, summarize_report
from pipeline_lib import write_json


STEPS = [
    "20_audit_score_normalisation.py",
    "21_audit_bathymetry_features.py",
    "22_audit_feature_bias.py",
    "23_generate_bias_aware_background.py",
    "24_spatiotemporal_validation.py",
    "25_retrain_corrected_models.py",
    "26_generate_corrected_prediction_map.py",
]


def run_step(script: str) -> dict:
    path = Path(__file__).with_name(script)
    print(f"\n=== {script} ===")
    proc = subprocess.run([sys.executable, str(path)], text=True, capture_output=True)
    if proc.stdout:
        print(proc.stdout[-4000:])
    if proc.stderr:
        print(proc.stderr[-4000:], file=sys.stderr)
    return {"script": script, "returncode": proc.returncode, "stdout_tail": proc.stdout[-2000:], "stderr_tail": proc.stderr[-2000:]}


def write_summary(step_results: list[dict]) -> dict:
    payload = summarize_report()
    payload["step_results"] = step_results
    write_json(AUDIT_ROOT / "model_audit_summary.json", payload)
    lines = [
        "# Model Audit Summary",
        "",
        "Current model outputs are under audit because nearshore score saturation was observed. Do not use old saturated outputs as real predictions.",
        "",
        "The model output is relative habitat suitability / hotspot score only. It is not exact fish location, guaranteed fish presence, live fish GPS, or true catch probability.",
        "",
        "## Step Results",
    ]
    for item in step_results:
        lines.append(f"- {item['script']}: return code `{item['returncode']}`")
    lines.append("")
    lines.append("## Species Summary")
    for species_id in TARGET_SPECIES:
        species = payload["species"].get(species_id, {})
        score_files = species.get("score_audit", {}).get("files", [])
        saturated = any(file.get("saturation") for file in score_files if isinstance(file, dict))
        clipped = any(file.get("clipping_or_normalisation_issue") for file in score_files if isinstance(file, dict))
        corrected = species.get("corrected_model", {})
        pred = load_json(AUDIT_ROOT.parents[0] / "predictions_corrected" / "corrected_prediction_summary.json", {})
        lines.extend(
            [
                f"### {species_id}",
                "",
                f"- old score saturation detected: `{saturated}`",
                f"- old clipping/normalisation issue detected: `{clipped}`",
                f"- corrected model status: `{corrected.get('status', 'unavailable')}`",
                f"- corrected model type: `{corrected.get('model_type', 'unavailable')}`",
                f"- confidence: `{corrected.get('confidence_level', 'unavailable')}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Fixes Applied",
            "",
            "- Existing prediction manifest entries are marked with an under-audit warning.",
            "- Score normalisation is audited for saturation and clipping.",
            "- Bathymetry/depth and ocean-mask features are audited.",
            "- Null models and coordinate/depth/month bias checks are run.",
            "- Bias-aware background strategies are generated separately from the original training data.",
            "- Corrected models are trained into `data/processed/models_corrected/` without overwriting original models.",
            "- Corrected maps are exported into `data/processed/predictions_corrected/` using strict percentile ranking.",
            "- Corrected rating thresholds are Prime top 5%, Good 5-15%, Possible 15-40%, Low bottom 60%.",
            "",
            "## Remaining Limitations",
            "",
            "- Public occurrence data is presence-only and biased by observation/fishing effort.",
            "- Background samples are pseudo-absence / available environment samples, not confirmed absence.",
            "- Independent validation with catch/no-catch effort, verified FADs, currents, chlorophyll, and tagging data is still needed.",
        ]
    )
    (AUDIT_ROOT / "MODEL_AUDIT_SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    return payload


def main() -> None:
    ensure_audit_dirs()
    results = [run_step(step) for step in STEPS]
    summary = write_summary(results)
    print(json.dumps({"status": "completed", "summary": str(AUDIT_ROOT / "MODEL_AUDIT_SUMMARY.md")}, indent=2))
    if any(item["returncode"] != 0 for item in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
