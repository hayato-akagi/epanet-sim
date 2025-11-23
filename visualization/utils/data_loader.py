import os
import json
import glob
import pandas as pd
import streamlit as st

def load_config(exp_path):
    """設定ファイルを読み込む"""
    config_files = glob.glob(os.path.join(exp_path, "*_config.json"))
    config_data = {}
    inp_filename = "Net1.inp"
    control_mode = "pressure"
    control_loops = []
    
    if config_files:
        with open(config_files[0], 'r') as f:
            config_data = json.load(f)
            inp_filename = config_data.get('network', {}).get('inp_file', 'Net1.inp')
            control_mode = config_data.get('control_mode', 'pressure')
            control_loops = config_data.get('control_loops', [])
    
    return config_data, inp_filename, control_mode, control_loops

def load_experiment_data(exp_path, control_mode):
    """実験結果データを読み込む"""
    result_csv = os.path.join(exp_path, "result.csv")
    
    if not os.path.exists(result_csv):
        st.error(f"Result CSV not found in {exp_path}")
        st.stop()
    
    df = pd.read_csv(result_csv)
    
    # CSVから制御モードを取得（設定ファイルがない場合）
    if 'ControlMode' in df.columns:
        control_mode = df['ControlMode'].iloc[0]
    
    # ループの検出
    has_multiple_loops = 'LoopID' in df.columns
    if has_multiple_loops:
        loop_ids = df['LoopID'].unique()
    else:
        loop_ids = ['default']
    
    return df, has_multiple_loops, loop_ids