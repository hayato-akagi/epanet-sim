#!/bin/bash
# 複数エピソード実行スクリプト（改善版）
# 各エピソード間でcontroller-vlaをリセット

set -e

# Load .env file if exists
if [ -f .env ]; then
    echo "Loading .env file..."
    export $(grep -v '^#' .env | xargs)
fi

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
        
        # ヘッダーから列番号を検出
        HEADER=$(head -1 shared/results/$EXP_ID/training_episodes.csv)
        IFS=',' read -ra COLUMNS <<< "$HEADER"
        ep_col=0
        mae_col=0
        rmse_col=0
        actor_col=0
        critic_col=0
        
        for idx in "${!COLUMNS[@]}"; do
            col="${COLUMNS[$idx]}"
            # ★ CRITICAL FIX: 完全一致のみ（^...$で囲む）
            # episode_reward, episode_steps などを除外
            if [[ "$col" =~ ^episode$ ]]; then
                ep_col=$((idx+1))
            elif [[ "$col" =~ ^mae$ ]]; then
                mae_col=$((idx+1))
            elif [[ "$col" =~ ^rmse$ ]]; then
                rmse_col=$((idx+1))
            elif [[ "$col" =~ ^mean_actor_loss$ ]] || [[ "$col" =~ ^actor_loss$ ]]; then
                actor_col=$((idx+1))
            elif [[ "$col" =~ ^mean_critic_loss$ ]] || [[ "$col" =~ ^critic_loss$ ]]; then
                critic_col=$((idx+1))
            fi
        done
        
        # デバッグ: 検出した列番号を表示（初回のみ）
        if [ $i -eq 1 ]; then
            echo "  [DEBUG] Detected columns: ep=$ep_col, mae=$mae_col, rmse=$rmse_col, actor=$actor_col, critic=$critic_col"
        fi
        
        # 最新行を表示
        tail -1 shared/results/$EXP_ID/training_episodes.csv | \
            awk -F',' -v ep=$ep_col -v mae=$mae_col -v rmse=$rmse_col -v actor=$actor_col -v critic=$critic_col '
            {
                if (ep > 0) printf "  Episode: %d\n", int($ep)
                if (mae > 0) printf "  MAE: %.2f m\n", $mae
                if (rmse > 0) printf "  RMSE: %.2f m\n", $rmse
                if (actor > 0) printf "  Actor Loss: %.4f\n", $actor
                if (critic > 0) printf "  Critic Loss: %.4f\n", $critic
            }' 2>/dev/null || echo "  Could not parse statistics"
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
    
    # ヘッダー行を取得して列番号を検出
    HEADER=$(head -1 shared/results/$EXP_ID/training_episodes.csv)
    IFS=',' read -ra COLUMNS <<< "$HEADER"
    ep_col=0
    mae_col=0
    rmse_col=0
    actor_col=0
    critic_col=0
    
    for idx in "${!COLUMNS[@]}"; do
        col="${COLUMNS[$idx]}"
        # ★ CRITICAL FIX: 完全一致のみ
        if [[ "$col" =~ ^episode$ ]]; then
            ep_col=$((idx+1))
        elif [[ "$col" =~ ^mae$ ]]; then
            mae_col=$((idx+1))
        elif [[ "$col" =~ ^rmse$ ]]; then
            rmse_col=$((idx+1))
        elif [[ "$col" =~ ^mean_actor_loss$ ]] || [[ "$col" =~ ^actor_loss$ ]]; then
            actor_col=$((idx+1))
        elif [[ "$col" =~ ^mean_critic_loss$ ]] || [[ "$col" =~ ^critic_loss$ ]]; then
            critic_col=$((idx+1))
        fi
    done
    
    echo "Detected columns: episode=$ep_col, mae=$mae_col, rmse=$rmse_col, actor=$actor_col, critic=$critic_col"
    echo ""
    
    # 列が正しく検出されたか確認
    if [ $ep_col -eq 0 ]; then
        echo "⚠️  ERROR: 'episode' column not found!"
        echo "Available columns:"
        echo "$HEADER" | tr ',' '\n' | nl
        echo ""
        echo "Showing raw data instead:"
        tail -n +2 shared/results/$EXP_ID/training_episodes.csv | tail -$NUM_EPISODES
    else
        echo "Episode | MAE (m) | RMSE (m) | Actor Loss | Critic Loss"
        echo "--------|---------|----------|------------|------------"
        
        # データ行を表示（整数でエピソード番号を表示）
        tail -n +2 shared/results/$EXP_ID/training_episodes.csv | tail -$NUM_EPISODES | \
            awk -F',' -v ep=$ep_col -v mae=$mae_col -v rmse=$rmse_col -v actor=$actor_col -v critic=$critic_col '
            {
                if (ep > 0 && mae > 0 && rmse > 0 && actor > 0 && critic > 0) {
                    printf "%-7d | %-7.2f | %-8.2f | %-10.4f | %-11.4f\n", 
                           int($ep), $mae, $rmse, $actor, $critic
                }
            }' 2>/dev/null
    fi
else
    echo ""
    echo "⚠️  training_episodes.csv not found!"
    echo "   Expected location: shared/results/$EXP_ID/training_episodes.csv"
    
    # デバッグ情報
    echo ""
    echo "Available files in result directory:"
    ls -lh shared/results/$EXP_ID/ 2>/dev/null || echo "  Directory not found"
fi

echo ""
echo "Results saved to: shared/results/$EXP_ID/"
echo ""
echo "To shutdown services:"
echo "  docker-compose down"