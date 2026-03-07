#!/usr/bin/env python3
import argparse
import csv
import itertools
import json
import os
import subprocess
import sys
import time
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent
CONFIG_DIR = ROOT / "shared" / "configs"
RESULT_DIR = ROOT / "shared" / "results"
RUNTIME_MODE = "host"

PID_BASE_FILE = CONFIG_DIR / "exp_pid_net1_flow_fair.json"
VLA_BASE_FILE = CONFIG_DIR / "exp_vla_net1_flow_fair.json"

PID_TUNED_FILE = CONFIG_DIR / "exp_pid_net1_flow_tuned.json"
VLA_TUNED_FILE = CONFIG_DIR / "exp_vla_net1_flow_tuned.json"


def run_cmd(cmd: str, env: Optional[dict] = None) -> None:
    print(f"\n$ {cmd}")
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    subprocess.run(cmd, shell=True, check=True, cwd=ROOT, env=merged_env)


def compose_down_if_needed() -> None:
    if RUNTIME_MODE == "host":
        run_cmd("docker compose down --remove-orphans || true")


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: dict) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def read_metrics_row(exp_id: str) -> dict:
    metrics_path = RESULT_DIR / exp_id / "metrics.csv"
    if not metrics_path.exists():
        raise FileNotFoundError(f"metrics.csv not found: {metrics_path}")

    with metrics_path.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        raise ValueError(f"metrics.csv is empty: {metrics_path}")

    all_row = next((r for r in rows if r.get("LoopID") == "ALL"), None)
    return all_row if all_row else rows[0]


def as_float(row: dict, key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key, default))
    except (TypeError, ValueError):
        return default


def score_from_metrics(row: dict) -> float:
    mae = as_float(row, "MAE")
    rmse = as_float(row, "RMSE")
    iae = as_float(row, "IAE")
    max_error = as_float(row, "MaxError")
    tv = as_float(row, "TotalVariation")

    return mae + 0.35 * rmse + 0.0001 * iae + 0.05 * max_error + 0.02 * tv


def wait_metrics(exp_id: str, timeout_sec: int = 60) -> dict:
    metrics_path = RESULT_DIR / exp_id / "metrics.csv"
    start = time.time()
    while time.time() - start <= timeout_sec:
        if metrics_path.exists() and metrics_path.stat().st_size > 0:
            return read_metrics_row(exp_id)
        time.sleep(2)
    raise TimeoutError(f"Timed out waiting metrics: {metrics_path}")


def run_pid_trial(exp_id: str, config_name: str) -> dict:
    compose_down_if_needed()
    run_cmd("docker compose up -d metrics-calculator")

    env = {
        "EXP_ID": exp_id,
        "EXP_CONFIG_FILE": config_name,
        "CONTROLLER_HOST": "controller-pid",
        "SAVE_IMAGES": "false",
    }
    run_cmd("docker compose up --build --abort-on-container-exit sim_runner", env=env)

    row = wait_metrics(exp_id, timeout_sec=90)
    compose_down_if_needed()
    return row


def run_vla_trial(exp_id: str, config_name: str, episodes: int, model: str) -> dict:
    compose_down_if_needed()

    base_env = {
        "EXP_ID": exp_id,
        "EXP_CONFIG_FILE": config_name,
        "CONTROLLER_HOST": "controller_vla",
        "VLA_MODEL": model,
        "VLA_AUTO_RESUME": "true",
        "SAVE_IMAGES": "false",
    }

    run_cmd(
        "docker compose up -d redis image-generator data-collector metrics-calculator controller_vla",
        env=base_env,
    )

    # give services time to initialize
    time.sleep(8)

    for i in range(1, episodes + 1):
        if i > 1:
            run_cmd("docker compose restart controller_vla", env=base_env)
            time.sleep(4)
        run_cmd("docker compose up --build --abort-on-container-exit sim_runner", env=base_env)
        time.sleep(3)

    row = wait_metrics(exp_id, timeout_sec=120)
    compose_down_if_needed()
    return row


def build_pid_candidates(base_cfg: dict, max_candidates: int) -> list[tuple[dict, dict]]:
    base = base_cfg["control_loops"][0]["pid_params"]
    kp0, ki0, kd0 = float(base["Kp"]), float(base["Ki"]), float(base["Kd"])

    candidates = []
    for kp_mul, ki_mul, kd_mul in itertools.product([0.5, 1.0, 1.5], [0.5, 1.0, 1.5], [0.7, 1.0, 1.3]):
        cfg = deepcopy(base_cfg)
        pid = cfg["control_loops"][0]["pid_params"]
        pid["Kp"] = round(kp0 * kp_mul, 8)
        pid["Ki"] = round(ki0 * ki_mul, 8)
        pid["Kd"] = round(kd0 * kd_mul, 8)

        meta = {"Kp": pid["Kp"], "Ki": pid["Ki"], "Kd": pid["Kd"]}
        candidates.append((cfg, meta))

    uniq = []
    seen = set()
    for cfg, meta in candidates:
        key = (meta["Kp"], meta["Ki"], meta["Kd"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append((cfg, meta))

    return uniq[:max_candidates]


def build_vla_candidates(base_cfg: dict, max_candidates: int) -> list[tuple[dict, dict]]:
    variants: list[tuple[str, dict]] = [
        (
            "baseline",
            {
                "learning_rate_actor": 3e-4,
                "learning_rate_critic": 3e-4,
                "learning_rate_alpha": 3e-4,
                "alpha": 0.2,
                "tracking_weight": 1.0,
                "stability_weight": 0.5,
                "delta_range": [-0.1, 0.1],
                "initial_random_steps": 50,
            },
        ),
        (
            "tracking_focus",
            {
                "learning_rate_actor": 3e-4,
                "learning_rate_critic": 3e-4,
                "learning_rate_alpha": 3e-4,
                "alpha": 0.15,
                "tracking_weight": 1.5,
                "stability_weight": 0.4,
                "delta_range": [-0.12, 0.12],
                "initial_random_steps": 40,
            },
        ),
        (
            "smooth_control",
            {
                "learning_rate_actor": 2e-4,
                "learning_rate_critic": 2e-4,
                "learning_rate_alpha": 2e-4,
                "alpha": 0.1,
                "tracking_weight": 1.2,
                "stability_weight": 0.9,
                "delta_range": [-0.06, 0.06],
                "initial_random_steps": 30,
            },
        ),
        (
            "fast_adapt",
            {
                "learning_rate_actor": 5e-4,
                "learning_rate_critic": 5e-4,
                "learning_rate_alpha": 3e-4,
                "alpha": 0.25,
                "tracking_weight": 1.2,
                "stability_weight": 0.6,
                "delta_range": [-0.15, 0.15],
                "initial_random_steps": 70,
            },
        ),
    ]

    out: list[tuple[dict, dict]] = []
    for name, p in variants[:max_candidates]:
        cfg = deepcopy(base_cfg)
        vla = cfg["control_loops"][0]["vla_params"]

        vla["training"]["learning_rate_actor"] = p["learning_rate_actor"]
        vla["training"]["learning_rate_critic"] = p["learning_rate_critic"]
        vla["training"]["learning_rate_alpha"] = p["learning_rate_alpha"]
        vla["training"]["alpha"] = p["alpha"]
        vla["reward"]["tracking_weight"] = p["tracking_weight"]
        vla["reward"]["stability_weight"] = p["stability_weight"]
        vla["action"]["delta_range"] = p["delta_range"]
        vla["exploration"]["initial_random_steps"] = p["initial_random_steps"]

        out.append((cfg, {"variant": name, **p}))

    return out


def write_summary_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    fieldnames = sorted({k for r in rows for k in r.keys()})
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    global RUNTIME_MODE
    parser = argparse.ArgumentParser(description="Auto-tune Net1 flow PID/VLA settings")
    parser.add_argument("--pid-candidates", type=int, default=8)
    parser.add_argument("--vla-candidates", type=int, default=4)
    parser.add_argument("--vla-episodes", type=int, default=8)
    parser.add_argument("--tuning-duration", type=int, default=21600, help="seconds; faster tuning duration")
    parser.add_argument("--hydraulic-step", type=int, default=600)
    parser.add_argument("--final-duration", type=int, default=86400)
    parser.add_argument("--vla-model", type=str, default="dummy")
    parser.add_argument("--runtime-mode", choices=["host", "container"], default="host")
    parser.add_argument("--run-final", action="store_true", help="Run final comparison using tuned configs")
    args = parser.parse_args()
    RUNTIME_MODE = args.runtime_mode

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary_rows: list[dict] = []

    pid_base = load_json(PID_BASE_FILE)
    vla_base = load_json(VLA_BASE_FILE)

    for cfg in (pid_base, vla_base):
        cfg["simulation"]["duration"] = args.tuning_duration
        cfg["simulation"]["hydraulic_step"] = args.hydraulic_step

    print("=== PID tuning ===")
    pid_best = None
    pid_best_score = float("inf")

    pid_candidates = build_pid_candidates(pid_base, args.pid_candidates)
    for idx, (cfg, meta) in enumerate(pid_candidates, start=1):
        exp_id = f"tune_pid_{timestamp}_{idx:02d}"
        cfg_name = f"_auto_{exp_id}.json"
        save_json(CONFIG_DIR / cfg_name, cfg)

        print(f"\n[PID {idx}/{len(pid_candidates)}] {meta}")
        row = run_pid_trial(exp_id, cfg_name)
        score = score_from_metrics(row)

        entry = {
            "kind": "PID",
            "exp_id": exp_id,
            "score": score,
            **meta,
            "MAE": as_float(row, "MAE"),
            "RMSE": as_float(row, "RMSE"),
            "IAE": as_float(row, "IAE"),
            "MaxError": as_float(row, "MaxError"),
            "TotalVariation": as_float(row, "TotalVariation"),
        }
        summary_rows.append(entry)

        if score < pid_best_score:
            pid_best_score = score
            pid_best = (deepcopy(cfg), deepcopy(meta), deepcopy(entry))

    if not pid_best:
        print("PID tuning failed")
        return 1

    pid_final_cfg = pid_best[0]
    pid_final_cfg["simulation"]["duration"] = args.final_duration
    pid_final_cfg["simulation"]["hydraulic_step"] = args.hydraulic_step
    save_json(PID_TUNED_FILE, pid_final_cfg)
    print(f"\nBest PID: {pid_best[1]} score={pid_best_score:.6f}")
    print(f"Saved tuned PID config: {PID_TUNED_FILE}")

    print("\n=== VLA tuning ===")
    vla_best = None
    vla_best_score = float("inf")

    vla_candidates = build_vla_candidates(vla_base, args.vla_candidates)
    for idx, (cfg, meta) in enumerate(vla_candidates, start=1):
        exp_id = f"tune_vla_{timestamp}_{idx:02d}"
        cfg_name = f"_auto_{exp_id}.json"
        save_json(CONFIG_DIR / cfg_name, cfg)

        print(f"\n[VLA {idx}/{len(vla_candidates)}] {meta['variant']}")
        row = run_vla_trial(exp_id, cfg_name, episodes=args.vla_episodes, model=args.vla_model)
        score = score_from_metrics(row)

        entry = {
            "kind": "VLA",
            "exp_id": exp_id,
            "score": score,
            **meta,
            "MAE": as_float(row, "MAE"),
            "RMSE": as_float(row, "RMSE"),
            "IAE": as_float(row, "IAE"),
            "MaxError": as_float(row, "MaxError"),
            "TotalVariation": as_float(row, "TotalVariation"),
        }
        summary_rows.append(entry)

        if score < vla_best_score:
            vla_best_score = score
            vla_best = (deepcopy(cfg), deepcopy(meta), deepcopy(entry))

    if not vla_best:
        print("VLA tuning failed")
        return 1

    vla_final_cfg = vla_best[0]
    vla_final_cfg["simulation"]["duration"] = args.final_duration
    vla_final_cfg["simulation"]["hydraulic_step"] = args.hydraulic_step
    save_json(VLA_TUNED_FILE, vla_final_cfg)
    print(f"\nBest VLA: {vla_best[1]} score={vla_best_score:.6f}")
    print(f"Saved tuned VLA config: {VLA_TUNED_FILE}")

    summary_path = RESULT_DIR / f"net1_flow_tuning_summary_{timestamp}.csv"
    write_summary_csv(summary_path, summary_rows)
    print(f"\nSaved tuning summary: {summary_path}")

    print("\n=== Next command (final fair comparison) ===")
    print(
        "PID_CONFIG=exp_pid_net1_flow_tuned.json "
        "VLA_CONFIG=exp_vla_net1_flow_tuned.json "
        "./run_net1_flow_compare.sh 20"
    )

    if args.run_final:
        run_cmd(
            "PID_CONFIG=exp_pid_net1_flow_tuned.json "
            "VLA_CONFIG=exp_vla_net1_flow_tuned.json "
            "./run_net1_flow_compare.sh 20"
        )

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as e:
        print(f"Command failed with exit code {e.returncode}", file=sys.stderr)
        raise SystemExit(e.returncode)
    finally:
        try:
            if RUNTIME_MODE == "host":
                subprocess.run(
                    "docker compose down --remove-orphans || true",
                    shell=True,
                    check=False,
                    cwd=ROOT,
                )
        except Exception:
            pass
