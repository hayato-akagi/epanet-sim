import streamlit as st
import pandas as pd
import os
import json
import glob
from utils.data_loader import load_experiment_data, load_config, load_training_logs
from utils.constants import RESULTS_DIR, NETWORKS_DIR
from tabs.network_3d import render_network_3d
from tabs.control_performance import render_control_performance
from tabs.time_series import render_time_series
from tabs.metrics_view import render_metrics
from tabs.training_progress import render_training_progress

st.set_page_config(page_title="Water Control Viz", layout="wide")
st.title("Water Hydraulic Control Visualization")

# --- サイドバー: 実験の選択 ---
st.sidebar.header("Experiment Selection")

# 結果ディレクトリにある実験IDフォルダを取得
exp_dirs = [d for d in os.listdir(RESULTS_DIR) if os.path.isdir(os.path.join(RESULTS_DIR, d))]
exp_dirs.sort(reverse=True)

if not exp_dirs:
    st.warning("No experiment results found in shared/results.")
    st.stop()

selected_exp = st.sidebar.selectbox("Select Experiment ID", exp_dirs)
exp_path = os.path.join(RESULTS_DIR, selected_exp)

# --- データ読み込み ---
config_data, inp_filename, control_mode, control_loops = load_config(exp_path)
df, has_multiple_loops, loop_ids = load_experiment_data(exp_path, control_mode)

# 学習ログの読み込み
steps_df, episodes_df, has_training_logs = load_training_logs(exp_path)

# サイドバーに情報表示
if config_data:
    st.sidebar.success(f"Loaded Config")

if has_multiple_loops:
    st.sidebar.info(f"**Control Mode:** {control_mode.upper()}\n\n**Loops:** {len(loop_ids)}")
else:
    st.sidebar.info(f"**Control Mode:** {control_mode.upper()}")

# 学習ログの有無を表示
if has_training_logs:
    st.sidebar.success("📊 Training logs available")
    if steps_df is not None:
        st.sidebar.text(f"Steps: {len(steps_df):,}")
    if episodes_df is not None:
        st.sidebar.text(f"Episodes: {len(episodes_df)}")
else:
    st.sidebar.info("ℹ️ No training logs (non-VLA experiment)")

# --- タブ構成 ---
if has_training_logs:
    # VLA実験の場合: 学習タブを追加
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "3D Network",
        "Control Performance",
        "Time Series Analysis",
        "Metrics",
        "🎓 Training Progress"
    ])
    
    with tab1:
        render_network_3d(
            exp_path=exp_path,
            inp_filename=inp_filename,
            control_mode=control_mode,
            control_loops=control_loops,
            config_data=config_data
        )
    
    with tab2:
        render_control_performance(
            df=df,
            control_mode=control_mode,
            has_multiple_loops=has_multiple_loops,
            loop_ids=loop_ids
        )
    
    with tab3:
        render_time_series(
            df=df,
            has_multiple_loops=has_multiple_loops,
            loop_ids=loop_ids
        )
    
    with tab4:
        render_metrics(exp_path=exp_path)
    
    with tab5:
        render_training_progress(steps_df, episodes_df)

else:
    # 非VLA実験の場合: 従来のタブのみ
    tab1, tab2, tab3, tab4 = st.tabs([
        "3D Network",
        "Control Performance",
        "Time Series Analysis",
        "Metrics"
    ])
    
    with tab1:
        render_network_3d(
            exp_path=exp_path,
            inp_filename=inp_filename,
            control_mode=control_mode,
            control_loops=control_loops,
            config_data=config_data
        )
    
    with tab2:
        render_control_performance(
            df=df,
            control_mode=control_mode,
            has_multiple_loops=has_multiple_loops,
            loop_ids=loop_ids
        )
    
    with tab3:
        render_time_series(
            df=df,
            has_multiple_loops=has_multiple_loops,
            loop_ids=loop_ids
        )
    
    with tab4:
        render_metrics(exp_path=exp_path)