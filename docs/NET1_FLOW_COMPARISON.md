# Net1 Flow: PID vs VLA 比較手順（公平化設定）

## 追加済みファイル

- `shared/networks/Net1_flow.inp`
- `shared/configs/exp_pid_net1_flow_fair.json`
- `shared/configs/exp_vla_net1_flow_fair.json`
- `run_net1_flow_compare.sh`
- `tune_net1_flow.py`

## 公平化の内容

- 同一ネットワーク: `Net1_flow.inp`
- 同一制御モード: `flow`
- 同一シミュレーション条件: `duration=86400`, `hydraulic_step=600`
- 同一アクチュエータ範囲: `min_setting=0.1`, `max_setting=1.0`
- 同一目標: `target_flow=1200.0`（Net1の`Units=GPM`）
- 既定VLAモデル: `openvla`

## 実行

```bash
chmod +x run_net1_flow_compare.sh
./run_net1_flow_compare.sh 20
```

- 引数 `20` は VLA のエピソード数
- PID の試行回数は環境変数で指定（デフォルト3）

```bash
PID_RUNS=5 ./run_net1_flow_compare.sh 20
```

`run_net1_flow_compare.sh` は `VLA_MODEL` 未指定時に `openvla` を使用します。

```bash
# 明示指定したい場合
VLA_MODEL=openvla ./run_net1_flow_compare.sh 20
```

## 自動調整（PID/VLA）

まず短時間条件で候補を探索し、最良設定を `*_tuned.json` として保存します。

```bash
python3 tune_net1_flow.py --pid-candidates 8 --vla-candidates 4 --vla-episodes 8
```

`tune_net1_flow.py` も既定で `--vla-model openvla` です。

コンテナ上で実行する場合（Compose管理）:

```bash
docker compose build experiment-tuner
HOST_PROJECT_DIR=$PWD docker compose run --rm --entrypoint "" experiment-tuner \
	python3 tune_net1_flow.py --runtime-mode container --pid-candidates 8 --vla-candidates 4 --vla-episodes 8
```

- 出力設定:
	- `shared/configs/exp_pid_net1_flow_tuned.json`
	- `shared/configs/exp_vla_net1_flow_tuned.json`
- 探索ログ:
	- `shared/results/net1_flow_tuning_summary_<timestamp>.csv`

探索後は tuned 設定で公平比較を実行します。

```bash
PID_CONFIG=exp_pid_net1_flow_tuned.json \
VLA_CONFIG=exp_vla_net1_flow_tuned.json \
./run_net1_flow_compare.sh 20
```

> 参考: 探索を軽くしたい場合は `--tuning-duration 10800` や `--pid-candidates 5` を指定してください。

## 別環境での再現（OpenVLA）

ここでは以下2つの検証を再現します。

1. 固定目標の公平化比較（`target_flow=1200`）
2. 時変目標（急変点あり）の比較

### 前提

- このリポジトリを clone した状態
- `docker compose` が利用可能

### 1) 固定目標の公平化比較（OpenVLA）

使用 config:

- PID: `shared/configs/exp_pid_net1_flow_tuned.json`
- VLA: `shared/configs/exp_vla_net1_flow_tuned.json`

実行:

```bash
VLA_MODEL=openvla \
PID_CONFIG=exp_pid_net1_flow_tuned.json \
VLA_CONFIG=exp_vla_net1_flow_tuned.json \
PID_RUNS=3 \
./run_net1_flow_compare.sh 3
```

結果:

- `shared/results/net1_flow_compare_<timestamp>_pid_r1`
- `shared/results/net1_flow_compare_<timestamp>_pid_r2`
- `shared/results/net1_flow_compare_<timestamp>_pid_r3`
- `shared/results/net1_flow_compare_<timestamp>_vla`

### 2) 時変目標（急変点あり）の比較（OpenVLA）

使用 config:

- PID: `shared/configs/exp_pid_net1_flow_profile_tuned.json`
- VLA: `shared/configs/exp_vla_net1_flow_profile_tuned.json`

急変プロファイル（`target_flow_profile`）:

- 0s: 1200
- 21600s: 1700
- 43200s: 900
- 64800s: 1500

実行:

```bash
VLA_MODEL=openvla \
PID_CONFIG=exp_pid_net1_flow_profile_tuned.json \
VLA_CONFIG=exp_vla_net1_flow_profile_tuned.json \
PID_RUNS=3 \
./run_net1_flow_compare.sh 6
```

結果:

- `shared/results/net1_flow_compare_<timestamp>_pid_r1`
- `shared/results/net1_flow_compare_<timestamp>_pid_r2`
- `shared/results/net1_flow_compare_<timestamp>_pid_r3`
- `shared/results/net1_flow_compare_<timestamp>_vla`

### 参考: コンテナ上でチューニングも再現する場合

```bash
docker compose build experiment-tuner
HOST_PROJECT_DIR=$PWD docker compose run --rm --entrypoint "" experiment-tuner \
	python3 tune_net1_flow.py --runtime-mode container --pid-candidates 5 --vla-candidates 3 --vla-episodes 3 --target-flow 1200 --vla-model openvla
```

## 出力

- PID: `shared/results/<prefix>_pid_r1`, `..._pid_r2`, ...
- VLA: `shared/results/<prefix>_vla`
- 各ディレクトリに `result.csv`, `metrics.csv`（VLAは `training_episodes.csv` も）

## 比較時に見る指標

- 追従精度: `MAE`, `RMSE`, `IAE`, `MaxError`
- 操作の滑らかさ: `TotalVariation`
- 補助: `MeanFlow`

VLA優位を示す際は、PID平均（複数run）に対して VLA最終エピソード近傍の指標を比較してください。
