#!/bin/bash
set -euo pipefail

VLA_EPISODES=${1:-20}
PID_RUNS=${PID_RUNS:-3}
EXP_PREFIX=${EXP_PREFIX:-net1_flow_compare_$(date +%Y%m%d_%H%M%S)}

PID_CONFIG=${PID_CONFIG:-exp_pid_net1_flow_fair.json}
VLA_CONFIG=${VLA_CONFIG:-exp_vla_net1_flow_fair.json}

print_summary() {
  local exp_id="$1"
  local metrics_file="shared/results/${exp_id}/metrics.csv"

  if [[ ! -f "$metrics_file" ]]; then
    echo "[WARN] metrics.csv not found for ${exp_id}"
    return
  fi

  echo "--- ${exp_id} summary ---"
  python3 - "$metrics_file" << 'PY'
import sys
import csv

metrics_path = sys.argv[1]

with open(metrics_path, "r", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

if not rows:
    raise SystemExit("metrics.csv is empty")

row = next((r for r in rows if r.get("LoopID") == "ALL"), rows[0])

keys = ['MAE', 'RMSE', 'IAE', 'MaxError', 'TotalVariation', 'MeanFlow']
for k in keys:
    if k in row and row[k] not in (None, ""):
        print(f"{k}: {float(row[k]):.6f}")
PY
  echo "metrics: ${metrics_file}"
  echo
}

echo "=========================================="
echo "Net1 Flow PID vs VLA fair comparison"
echo "EXP_PREFIX=${EXP_PREFIX}"
echo "PID_RUNS=${PID_RUNS}, VLA_EPISODES=${VLA_EPISODES}"
echo "=========================================="

# Safety cleanup
docker compose down --remove-orphans >/dev/null 2>&1 || true

# -----------------------------
# PID baseline runs
# -----------------------------
echo
echo "[1/2] Running PID baseline (${PID_RUNS} runs)..."
for i in $(seq 1 "$PID_RUNS"); do
  exp_id="${EXP_PREFIX}_pid_r${i}"
  echo "\nPID run ${i}/${PID_RUNS}: ${exp_id}"

  rm -rf "shared/results/${exp_id}"

  docker compose up -d metrics-calculator

  EXP_ID="$exp_id" \
  EXP_CONFIG_FILE="$PID_CONFIG" \
  CONTROLLER_HOST=controller-pid \
  SAVE_IMAGES=false \
  docker compose up --build --abort-on-container-exit sim_runner

  # metrics-calculator polling wait
  sleep 8

  docker compose down --remove-orphans

  print_summary "$exp_id"
done

# -----------------------------
# VLA training/eval run
# -----------------------------
echo
echo "[2/2] Running VLA (${VLA_EPISODES} episodes)..."
vla_exp_id="${EXP_PREFIX}_vla"
rm -rf "shared/results/${vla_exp_id}"

EXP_ID="$vla_exp_id" \
EXP_CONFIG_FILE="$VLA_CONFIG" \
CONTROLLER_HOST=controller_vla \
VLA_MODEL=dummy \
VLA_AUTO_RESUME=true \
SAVE_IMAGES=false \
docker compose up -d redis image-generator data-collector metrics-calculator controller_vla

sleep 8

for i in $(seq 1 "$VLA_EPISODES"); do
  echo "\nVLA episode ${i}/${VLA_EPISODES}: ${vla_exp_id}"
  if [ "$i" -gt 1 ]; then
    EXP_ID="$vla_exp_id" \
    EXP_CONFIG_FILE="$VLA_CONFIG" \
    CONTROLLER_HOST=controller_vla \
    VLA_MODEL=dummy \
    VLA_AUTO_RESUME=true \
    SAVE_IMAGES=false \
    docker compose restart controller_vla
    sleep 4
  fi

  EXP_ID="$vla_exp_id" \
  EXP_CONFIG_FILE="$VLA_CONFIG" \
  CONTROLLER_HOST=controller_vla \
  VLA_MODEL=dummy \
  VLA_AUTO_RESUME=true \
  SAVE_IMAGES=false \
  docker compose up --build --abort-on-container-exit sim_runner

  sleep 3
done

docker compose down --remove-orphans

print_summary "$vla_exp_id"

echo "=========================================="
echo "Completed. Result directories:"
echo "  shared/results/${EXP_PREFIX}_pid_r*"
echo "  shared/results/${EXP_PREFIX}_vla"
echo "=========================================="
