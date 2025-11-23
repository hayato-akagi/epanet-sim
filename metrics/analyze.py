import os
import time
import pandas as pd
import numpy as np

# 環境変数設定
INPUT_DIR = os.environ.get('INPUT_PATH', '/shared/results')

def calculate_metrics(csv_path):
    """CSVファイルから制御性能指標を計算する"""
    try:
        df = pd.read_csv(csv_path)
        
        # 制御モードの判定
        if 'ControlMode' in df.columns:
            control_mode = df['ControlMode'].iloc[0]
        else:
            control_mode = 'pressure'  # デフォルト
        
        # 必要なカラムの確認（基本カラム）
        required_cols = ['Time', 'ValveSetting']
        if not all(col in df.columns for col in required_cols):
            return None
        
        # 制御対象値とターゲット値の取得
        if 'ControlledValue' in df.columns and 'TargetValue' in df.columns:
            # 新形式
            controlled = df['ControlledValue']
            target = df['TargetValue']
        else:
            # 旧形式（後方互換性）
            if control_mode == 'flow':
                if 'Flow' not in df.columns or 'TargetFlow' not in df.columns:
                    return None
                controlled = df['Flow']
                target = df['TargetFlow']
            else:
                if 'Pressure' not in df.columns or 'TargetPressure' not in df.columns:
                    return None
                controlled = df['Pressure']
                target = df['TargetPressure']

        # --- 前処理 ---
        dt = df['Time'].diff().mean()
        if pd.isna(dt): dt = 300.0

        # エラー計算
        if 'Error' in df.columns:
            error = df['Error']
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
        valve_diff = df['ValveSetting'].diff().abs().sum()
        mean_valve = df['ValveSetting'].mean()
        
        # 定常状態性能（後半50%）
        steady_idx = len(df) // 2
        steady_error = error.iloc[steady_idx:]
        steady_mae = steady_error.abs().mean()
        steady_rmse = np.sqrt((steady_error ** 2).mean())

        # CSV用のフラットな辞書を作成
        metrics = {
            "SourceFile": os.path.basename(csv_path),
            "ProcessedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
            "ControlMode": control_mode,
            "DurationSec": float(df['Time'].iloc[-1] - df['Time'].iloc[0]),
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
        if 'Pressure' in df.columns:
            metrics['MeanPressure'] = float(df['Pressure'].mean())
        if 'Flow' in df.columns:
            metrics['MeanFlow'] = float(df['Flow'].mean())
        
        return metrics

    except Exception as e:
        print(f"Error processing {csv_path}: {e}")
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
                        metrics_data = calculate_metrics(csv_path)
                        
                        if metrics_data:
                            # 辞書をDataFrameに変換してCSV保存
                            metrics_df = pd.DataFrame([metrics_data])
                            metrics_df.to_csv(metrics_path, index=False)
                            print(f"Saved metrics CSV to {metrics_path}")
        
        time.sleep(5)

if __name__ == "__main__":
    main()