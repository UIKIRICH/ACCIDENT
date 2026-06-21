import argparse
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd


def parse_feature_cols(columns: List[str]) -> List[str]:
    feat_cols = [c for c in columns if c.startswith("feature_")]
    feat_cols.sort(key=lambda c: int(c.split("_", 1)[1]))
    return feat_cols


def clip01(x: np.ndarray) -> np.ndarray:
    return np.clip(x, 0.0, 1.0)


def wrap_angle(x: np.ndarray) -> np.ndarray:
    return (x + np.pi) % (2 * np.pi) - np.pi


def resample_to(seq: np.ndarray, target_steps: int) -> np.ndarray:
    if seq.size == 0:
        return np.zeros((target_steps,), dtype=np.float32)
    if seq.size == target_steps:
        return seq.astype(np.float32)
    src_x = np.arange(seq.size, dtype=np.float32)
    dst_x = np.linspace(0, float(seq.size - 1), target_steps, dtype=np.float32)
    return np.interp(dst_x, src_x, seq.astype(np.float32)).astype(np.float32)


def robust_norm_diff(x: np.ndarray) -> np.ndarray:
    if x.size <= 1:
        return np.zeros_like(x, dtype=np.float32)
    d = np.zeros_like(x, dtype=np.float32)
    d[1:] = np.abs(np.diff(x.astype(np.float32)))
    scale = float(np.percentile(d[1:], 90)) if np.any(d[1:] > 0) else 1.0
    return clip01(d / max(scale, 1e-6)).astype(np.float32)


def extract_turn_motion_features(
    feature_vec: np.ndarray,
    target_steps: int,
    optical_offset: int,
    optical_steps: int,
    optical_dim: int,
    vehicle_offset: int,
    vehicle_dim: int,
) -> np.ndarray:
    optical_len = optical_steps * optical_dim
    optical_raw = np.zeros((optical_steps, optical_dim), dtype=np.float32)
    if feature_vec.size >= optical_offset + optical_len:
        optical_raw = feature_vec[optical_offset : optical_offset + optical_len].reshape(optical_steps, optical_dim)

    # From existing optical block layout:
    # [mean_mag, std_mag, max_mag, p90, p75, p25, mean_ang, std_ang, mean_vx, std_vx, mean_vy]
    mean_ang = optical_raw[:, 6]
    mean_vx = optical_raw[:, 8]
    mean_vy = optical_raw[:, 10]

    delta_ang = np.zeros((optical_steps,), dtype=np.float32)
    if optical_steps > 1:
        delta_ang[1:] = np.abs(wrap_angle(mean_ang[1:] - mean_ang[:-1])) / np.pi

    sign_flip = np.zeros((optical_steps,), dtype=np.float32)
    if optical_steps > 1:
        sign_flip[1:] = (
            (np.sign(mean_vx[1:]) * np.sign(mean_vx[:-1]) < 0)
            & ((np.abs(mean_vx[1:]) + np.abs(mean_vx[:-1])) > 1e-6)
        ).astype(np.float32)

    # 1) Trajectory crossing angle (cross tendency proxy)
    traj_cross = clip01(0.75 * delta_ang + 0.25 * sign_flip)

    # 2) Relative heading change (direction drift proxy)
    heading = np.arctan2(mean_vy, mean_vx + 1e-8)
    rel_heading = np.abs(wrap_angle(heading - heading[0])) / np.pi
    rel_heading = clip01(rel_heading)

    # 3) Lateral speed difference (cut-in intensity proxy)
    lat_delta = robust_norm_diff(mean_vx)
    veh_lat_delta = np.zeros((optical_steps,), dtype=np.float32)
    if feature_vec.size >= vehicle_offset + vehicle_dim and vehicle_dim >= 10:
        veh = feature_vec[vehicle_offset : vehicle_offset + vehicle_dim]
        veh = veh[: (vehicle_dim // 5) * 5].reshape(-1, 5)  # [num, x, y, w, h]
        veh_x = veh[:, 1].astype(np.float32)
        veh_lat_delta_small = robust_norm_diff(veh_x)
        veh_lat_delta = resample_to(veh_lat_delta_small, optical_steps)
    lat_speed_diff = clip01(0.7 * lat_delta + 0.3 * veh_lat_delta)

    # Resample all three sequences to target_steps and concatenate.
    traj_cross_59 = resample_to(traj_cross, target_steps)
    rel_heading_59 = resample_to(rel_heading, target_steps)
    lat_speed_diff_59 = resample_to(lat_speed_diff, target_steps)
    return np.concatenate([traj_cross_59, rel_heading_59, lat_speed_diff_59]).astype(np.float32)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build v3.3.2 turn-focused motion features from existing feature CSV.")
    parser.add_argument("--in-csv", required=True, help="Input feature CSV, e.g., full_features_with_id.csv")
    parser.add_argument("--out-csv", required=True, help="Output feature CSV with appended turn motion features")
    parser.add_argument("--target-steps", type=int, default=59, help="Target sequence steps for appended features")
    parser.add_argument("--optical-offset", type=int, default=32, help="Optical feature start index in base vector")
    parser.add_argument("--optical-steps", type=int, default=31, help="Optical temporal steps")
    parser.add_argument("--optical-dim", type=int, default=11, help="Optical stats per step")
    parser.add_argument("--vehicle-offset", type=int, default=373, help="Vehicle feature start index in base vector")
    parser.add_argument("--vehicle-dim", type=int, default=40, help="Vehicle feature length")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    in_csv = Path(args.in_csv).resolve()
    out_csv = Path(args.out_csv).resolve()
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(in_csv)
    feat_cols = parse_feature_cols(df.columns.tolist())
    if not feat_cols:
        raise RuntimeError(f"No feature_* columns found in {in_csv}")

    base_mat = df[feat_cols].to_numpy(dtype=np.float32)
    base_dim = base_mat.shape[1]
    append_dim = int(args.target_steps) * 3

    append_rows = np.zeros((base_mat.shape[0], append_dim), dtype=np.float32)
    for i in range(base_mat.shape[0]):
        append_rows[i] = extract_turn_motion_features(
            feature_vec=base_mat[i],
            target_steps=int(args.target_steps),
            optical_offset=int(args.optical_offset),
            optical_steps=int(args.optical_steps),
            optical_dim=int(args.optical_dim),
            vehicle_offset=int(args.vehicle_offset),
            vehicle_dim=int(args.vehicle_dim),
        )
        if args.verbose and (i + 1) % 50 == 0:
            print(f"[INFO] processed {i + 1}/{base_mat.shape[0]}")

    start_idx = max(int(c.split("_", 1)[1]) for c in feat_cols) + 1
    append_cols = [f"feature_{start_idx + j}" for j in range(append_dim)]
    append_df = pd.DataFrame(append_rows, columns=append_cols, index=df.index)
    new_df = pd.concat([df, append_df], axis=1)

    new_feat_cols = parse_feature_cols(new_df.columns.tolist())
    new_df.to_csv(out_csv, index=False)

    print(
        f"[DONE] in_rows={len(df)}, in_feat_dim={base_dim}, "
        f"append_dim={append_dim}, out_feat_dim={len(new_feat_cols)}"
    )
    print(f"[OUT] {out_csv}")


if __name__ == "__main__":
    main()
