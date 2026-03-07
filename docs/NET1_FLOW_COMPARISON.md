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
- 同一目標: `target_flow=100.0`（Net1の`Units=GPM`）

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

## 自動調整（PID/VLA）

まず短時間条件で候補を探索し、最良設定を `*_tuned.json` として保存します。

```bash
python3 tune_net1_flow.py --pid-candidates 8 --vla-candidates 4 --vla-episodes 8
```

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

## 出力

- PID: `shared/results/<prefix>_pid_r1`, `..._pid_r2`, ...
- VLA: `shared/results/<prefix>_vla`
- 各ディレクトリに `result.csv`, `metrics.csv`（VLAは `training_episodes.csv` も）

## 比較時に見る指標

- 追従精度: `MAE`, `RMSE`, `IAE`, `MaxError`
- 操作の滑らかさ: `TotalVariation`
- 補助: `MeanFlow`

VLA優位を示す際は、PID平均（複数run）に対して VLA最終エピソード近傍の指標を比較してください。
