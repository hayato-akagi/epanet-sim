import os
import time
import pandas as pd
import numpy as np

# 環境変数設定
INPUT_DIR = os.environ.get('INPUT_PATH', '/shared/results')

def calculate_loop_metrics(df_loop, loop_id, control_mode):
    """1つのループに対するメトリクスを計算"""
    # 制御対象値とターゲット値の取得
    if 'ControlledValue' in df_loop.columns and 'TargetValue' in df_loop.columns:
        # 新形式
        controlled = df_loop['ControlledValue']
        target = df_loop['TargetValue']
    else:
        # 旧形式（後方互換性）
        if control_mode == 'flow':
            if 'Flow' not in df_loop.columns or 'TargetFlow' not in df_loop.columns:
                return None
            controlled = df_loop['Flow']
            target = df_loop['TargetFlow']
        else:
            if 'Pressure' not in df_loop.columns or 'TargetPressure' not in df_loop.columns:
                return None
            controlled = df_loop['Pressure']
            target = df_loop['TargetPressure']
    
    # --- 前処理 ---
    dt = df_loop['Time'].diff().mean()
    if pd.isna(dt): 
        dt = 300.0
    
    # エラー計算
    if 'Error' in df_loop.columns:
        error = df_loop['Error']
    else:
        error = target - controlled
    
    abs_error = error.abs()
    squared_error = error ** 2
    
    # --- 指標計算 ---
    mae = abs_error.mean()
    rmse = np.sqrt(squared_error.mean())
    max_error = abs_error.max()
    iae = np.trapz(abs_error, dx=dt)
    ise = np.trapz(squared_error, dx=dt)
    
    # バルブ操作量
    if 'ValveSetting' in df_loop.columns:
        valve_diff = df_loop['ValveSetting'].diff().abs().sum()
        mean_valve = df_loop['ValveSetting'].mean()
    else:
        valve_diff = 0.0
        mean_valve = 0.0
    
    # 定常状態性能（後半50%）
    steady_idx = len(df_loop) // 2
    steady_error = error.iloc[steady_idx:]
    steady_mae = steady_error.abs().mean()
    steady_rmse = np.sqrt((steady_error ** 2).mean())
    
    # メトリクス辞書
    metrics = {
        "LoopID": loop_id,
        "ControlMode": control_mode,
        "NumSamples": len(df_loop),
        "TargetValue": float(target.iloc[0]) if len(target) > 0 else 0.0,
        "MeanControlledValue": float(controlled.mean()),
        "MAE": float(mae),
        "RMSE": float(rmse),
        "MaxError": float(max_error),
        "IAE": float(iae),
        "ISE": float(ise),
        "SteadyMAE": float(steady_mae),
        "SteadyRMSE": float(steady_rmse),
        "TotalVariation": float(valve_diff),
        "MeanValve": float(mean_valve)
    }
    
    # 圧力と流量の両方を記録（利用可能な場合）
    if 'Pressure' in df_loop.columns:
        metrics['MeanPressure'] = float(df_loop['Pressure'].mean())
    if 'Flow' in df_loop.columns:
        metrics['MeanFlow'] = float(df_loop['Flow'].mean())
    
    return metrics

def calculate_metrics(csv_path):
    """CSVファイルから制御性能指標を計算する（ループごと+全体）"""
    try:
        df = pd.read_csv(csv_path)
        
        # 制御モードの判定
        if 'ControlMode' in df.columns:
            control_mode = df['ControlMode'].iloc[0]
        else:
            control_mode = 'pressure'  # デフォルト
        
        # 必要なカラムの確認（基本カラム）
        required_cols = ['Time']
        if not all(col in df.columns for col in required_cols):
            return None
        
        # LoopIDカラムの有無を確認
        has_loop_id = 'LoopID' in df.columns
        
        all_metrics = []
        
        if has_loop_id:
            # 複数ループの場合: ループごとに計算
            loop_ids = df['LoopID'].unique()
            print(f"  Found {len(loop_ids)} control loops: {list(loop_ids)}")
            
            for loop_id in loop_ids:
                df_loop = df[df['LoopID'] == loop_id].copy()
                loop_metrics = calculate_loop_metrics(df_loop, loop_id, control_mode)
                
                if loop_metrics:
                    all_metrics.append(loop_metrics)
            
            # 全体の統合指標を計算
            if all_metrics:
                overall_metrics = {
                    "LoopID": "ALL",
                    "ControlMode": control_mode,
                    "NumSamples": len(df),
                    "NumLoops": len(loop_ids),
                    "MAE": np.mean([m['MAE'] for m in all_metrics]),
                    "RMSE": np.mean([m['RMSE'] for m in all_metrics]),
                    "MaxError": np.max([m['MaxError'] for m in all_metrics]),
                    "IAE": np.sum([m['IAE'] for m in all_metrics]),
                    "ISE": np.sum([m['ISE'] for m in all_metrics]),
                    "SteadyMAE": np.mean([m['SteadyMAE'] for m in all_metrics]),
                    "SteadyRMSE": np.mean([m['SteadyRMSE'] for m in all_metrics]),
                    "TotalVariation": np.sum([m['TotalVariation'] for m in all_metrics]),
                    "MeanValve": np.mean([m['MeanValve'] for m in all_metrics])
                }
                
                # 圧力・流量の全体平均
                if 'Pressure' in df.columns:
                    overall_metrics['MeanPressure'] = float(df['Pressure'].mean())
                if 'Flow' in df.columns:
                    overall_metrics['MeanFlow'] = float(df['Flow'].mean())
                
                all_metrics.append(overall_metrics)
        
        else:
            # 単一ループの場合（後方互換性）
            print(f"  Single loop (legacy format)")
            loop_metrics = calculate_loop_metrics(df, "default", control_mode)
            
            if loop_metrics:
                all_metrics.append(loop_metrics)
        
        if not all_metrics:
            return None
        
        # 共通メタデータを追加
        for metrics in all_metrics:
            metrics["SourceFile"] = os.path.basename(csv_path)
            metrics["ProcessedAt"] = time.strftime("%Y-%m-%d %H:%M:%S")
            if 'Time' in df.columns and len(df) > 0:
                metrics["DurationSec"] = float(df['Time'].iloc[-1] - df['Time'].iloc[0])
        
        return all_metrics
        
    except Exception as e:
        print(f"Error processing {csv_path}: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    print(f"Starting Recursive Metrics Watcher on {INPUT_DIR}...")
    
    while True:
        # os.walk でサブディレクトリも含めて探索
        for root, dirs, files in os.walk(INPUT_DIR):
            for file in files:
                if file.endswith(".csv") and "result" in file and "metrics" not in file:
                    csv_path = os.path.join(root, file)
                    
                    # 同じディレクトリに metrics.csv を保存
                    metrics_filename = "metrics.csv"
                    metrics_path = os.path.join(root, metrics_filename)
                    
                    # まだMetricsファイルがない、または結果ファイルの方が新しい場合に実行
                    should_process = False
                    if not os.path.exists(metrics_path):
                        should_process = True
                    else:
                        # 簡易的な更新チェック（タイムスタンプ比較）
                        if os.path.getmtime(csv_path) > os.path.getmtime(metrics_path):
                            should_process = True
                    
                    if should_process:
                        print(f"Processing new/updated result: {csv_path}")
                        metrics_data_list = calculate_metrics(csv_path)
                        
                        if metrics_data_list:
                            # リストをDataFrameに変換してCSV保存
                            metrics_df = pd.DataFrame(metrics_data_list)
                            metrics_df.to_csv(metrics_path, index=False)
                            print(f"Saved metrics CSV to {metrics_path}")
                            print(f"  Generated {len(metrics_data_list)} metric records")
        
        time.sleep(5)

if __name__ == "__main__":
    main()