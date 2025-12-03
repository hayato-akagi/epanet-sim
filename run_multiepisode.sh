#!/bin/bash

# 複数エピソード実行スクリプト（改善版）
# 各エピソード間でcontroller-vlaをリセット

set -e

NUM_EPISODES=${1:-10}
EXP_ID=${EXP_ID:-simplednn_correct_001}

echo "=========================================="
echo "Running $NUM_EPISODES episodes for $EXP_ID"
echo "=========================================="

# 初回：すべてのサービスを起動
echo ""
echo "=== Initial Setup ==="
echo "Starting all services..."
docker-compose up -d redis image-generator data-collector metrics-calculator

# 初回のcontroller-vla起動
echo "Starting controller-vla..."
docker-compose up -d controller-vla

# サービスが起動するまで待機
echo "Waiting for services to be ready..."
sleep 10

# 各エピソードを実行
for i in $(seq 1 $NUM_EPISODES); do
    echo ""
    echo "=========================================="
    echo "=== Episode $i / $NUM_EPISODES ==="
    echo "=========================================="
    
    # Episode 2以降はcontroller-vlaをリセット
    if [ $i -gt 1 ]; then
        echo "Resetting controller-vla..."
        docker-compose restart controller-vla
        sleep 5
    fi
    
    # sim-runnerを実行（フォアグラウンド）
    echo "Running sim-runner..."
    docker-compose up sim-runner
    
    # sim-runnerが終了したら次へ
    echo "Episode $i completed."
    
    # 短い待機（ログ書き込み完了を待つ）
    sleep 3
    
    # 現在の統計を表示
    if [ -f "shared/results/$EXP_ID/training_episodes.csv" ]; then
        echo ""
        echo "--- Current Statistics ---"
        tail -1 shared/results/$EXP_ID/training_episodes.csv | \
            awk -F',' '{printf "  Episode: %s\n  MAE: %.2f m\n  RMSE: %.2f m\n  Actor Loss: %.4f\n  Critic Loss: %.4f\n", $2, $11, $12, $7, $8}'
    fi
done

echo ""
echo "=========================================="
echo "All $NUM_EPISODES episodes completed!"
echo "=========================================="

# 最終結果を表示
if [ -f "shared/results/$EXP_ID/training_episodes.csv" ]; then
    echo ""
    echo "=== Final Results ==="
    echo ""
    echo "Episode | MAE (m) | RMSE (m) | Actor Loss | Critic Loss"
    echo "--------|---------|----------|------------|------------"
    tail -$NUM_EPISODES shared/results/$EXP_ID/training_episodes.csv | \
        awk -F',' 'NR>1 {printf "%-7s | %-7.2f | %-8.2f | %-10.4f | %-11.4f\n", $2, $11, $12, $7, $8}'
fi

echo ""
echo "Results saved to: shared/results/$EXP_ID/"
echo ""
echo "To shutdown services:"
echo "  docker-compose down"