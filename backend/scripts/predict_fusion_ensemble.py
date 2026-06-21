import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd
import torch
import torch.nn as nn


CLASS_NAMES = ["rear_end", "lane_change", "turn_conflict"]


def parse_json_dict(v: Any) -> Dict[str, Any]:
    if isinstance(v, dict):
        return v
    if isinstance(v, str) and v.strip():
        try:
            x = json.loads(v)
            return x if isinstance(x, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def parse_json_list(v: Any) -> List[Any]:
    if isinstance(v, list):
        return v
    if isinstance(v, str) and v.strip():
        try:
            x = json.loads(v)
            return x if isinstance(x, list) else []
        except json.JSONDecodeError:
            return []
    return []


def safe_float(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(d)


def featurize_row_legacy24(row: pd.Series) -> np.ndarray:
    probs = parse_json_dict(row.get("pred_type_probs", "{}"))
    scores = parse_json_dict(row.get("pred_type_scores", "{}"))
    dominant = parse_json_dict(row.get("dominant_meta", "{}"))
    scene_tags = parse_json_list(row.get("scene_tags", "[]"))

    f = [
        safe_float(probs.get("rear_end", 0.0)),
        safe_float(probs.get("lane_change", 0.0)),
        safe_float(probs.get("turn_conflict", 0.0)),
        safe_float(scores.get("rear_end", 0.0)),
        safe_float(scores.get("lane_change", 0.0)),
        safe_float(scores.get("turn_conflict", 0.0)),
        safe_float(row.get("pred_type_confidence", 0.0)),
        safe_float(row.get("risk_alert_time", 0.0)),
        safe_float(row.get("lead_time_sec", 0.0)),
        safe_float(row.get("uncertainty", 1.0)),
        safe_float(row.get("pred_onset_time", 0.0)),
        safe_float(row.get("pred_impact_time", 0.0)),
        safe_float(row.get("pred_post_time", 0.0)),
        safe_float(row.get("duration_seconds", 0.0)),
        safe_float(row.get("fps", 0.0)),
        safe_float(row.get("num_steps", 0.0)),
        safe_float(dominant.get("dominance", 0.0)),
        safe_float(dominant.get("coverage", 0.0)),
        safe_float(dominant.get("continuity", 0.0)),
        safe_float(dominant.get("impact_peak", 0.0)),
        1.0 if "intersection" in scene_tags else 0.0,
        1.0 if "turning_scene" in scene_tags else 0.0,
        1.0 if "night" in scene_tags else 0.0,
        1.0 if "rain" in scene_tags else 0.0,
    ]
    return np.array(f, dtype=np.float32)


class FusionMLP(nn.Module):
    def __init__(self, in_dim: int, hidden: int = 64) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(in_dim, hidden),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
            nn.Linear(hidden, len(CLASS_NAMES)),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


def softmax_np(logits: np.ndarray) -> np.ndarray:
    x = logits - logits.max(axis=1, keepdims=True)
    ex = np.exp(x)
    return ex / np.clip(ex.sum(axis=1, keepdims=True), 1e-12, None)


def resolve_checkpoints(checkpoints_dir: Path) -> List[Path]:
    cks = sorted(checkpoints_dir.glob("fold*_best.pt"))
    if not cks:
        raise FileNotFoundError(f"No checkpoints found under: {checkpoints_dir}")
    return cks


def main() -> None:
    parser = argparse.ArgumentParser(description="Predict with fusion checkpoint ensemble on meta parquet.")
    parser.add_argument("--meta", required=True, help="Meta parquet path")
    parser.add_argument("--checkpoints-dir", required=True, help="Directory containing fold*_best.pt")
    parser.add_argument("--out", required=True, help="Output prediction jsonl")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    meta_path = Path(args.meta).resolve()
    ckpt_dir = Path(args.checkpoints_dir).resolve()
    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(meta_path)
    if df.empty:
        raise RuntimeError(f"Empty meta parquet: {meta_path}")

    checkpoints = resolve_checkpoints(ckpt_dir)

    feats = np.stack([featurize_row_legacy24(r) for _, r in df.iterrows()])
    n_samples = feats.shape[0]

    prob_acc = np.zeros((n_samples, len(CLASS_NAMES)), dtype=np.float64)
    used = 0

    for ck in checkpoints:
        payload = torch.load(ck, map_location="cpu")
        mu = np.array(payload.get("feature_mean", []), dtype=np.float32).reshape(-1)
        std = np.array(payload.get("feature_std", []), dtype=np.float32).reshape(-1)
        if mu.size != 24 or std.size != 24:
            raise RuntimeError(
                f"{ck} expects dim={mu.size}, but this script currently supports legacy 24-dim checkpoints only."
            )

        x = (feats - mu.reshape(1, -1)) / np.clip(std.reshape(1, -1), 1e-6, None)
        xt = torch.tensor(x, dtype=torch.float32)

        model = FusionMLP(in_dim=24)
        model.load_state_dict(payload["model_state_dict"])
        model.eval()
        with torch.no_grad():
            logits = model(xt).numpy()
            probs = softmax_np(logits)
            prob_acc += probs
            used += 1

        if args.verbose:
            print(f"[INFO] used checkpoint: {ck.name}")

    if used <= 0:
        raise RuntimeError("No checkpoint used.")
    probs_mean = prob_acc / float(used)
    pred_idx = np.argmax(probs_mean, axis=1)

    with out_path.open("w", encoding="utf-8") as f:
        for i, (_, row) in enumerate(df.iterrows()):
            onset = safe_float(row.get("pred_onset_time", 0.0))
            impact = safe_float(row.get("pred_impact_time", 0.0))
            post = safe_float(row.get("pred_post_time", 0.0))
            scene_tags = [str(x) for x in parse_json_list(row.get("scene_tags", "[]"))]
            p = probs_mean[i]
            type_probs = {
                "rear_end": round(float(p[0]), 6),
                "lane_change": round(float(p[1]), 6),
                "turn_conflict": round(float(p[2]), 6),
                "generic": 0.0,
            }
            out = {
                "video": str(row.get("video", "")),
                "pred_type": CLASS_NAMES[int(pred_idx[i])],
                "type_probs": type_probs,
                "pred_onset_time": round(float(onset), 2),
                "pred_impact_time": round(float(impact), 2),
                "pred_post_time": round(float(post), 2),
                "lead_time_sec": round(float(max(0.0, safe_float(row.get("lead_time_sec", 0.0)))), 2),
                "risk_score": round(float(max(type_probs["rear_end"], type_probs["lane_change"], type_probs["turn_conflict"])), 6),
                "uncertainty": round(float(safe_float(row.get("uncertainty", 1.0))), 6),
                "keyframe_times": [round(float(x), 2) for x in [onset, impact, post] if float(x) >= 0.0],
                "scene_tags": scene_tags,
            }
            f.write(json.dumps(out, ensure_ascii=False) + "\n")

    print(
        json.dumps(
            {
                "meta": str(meta_path),
                "checkpoints_dir": str(ckpt_dir),
                "checkpoints_used": used,
                "rows": n_samples,
                "out": str(out_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
