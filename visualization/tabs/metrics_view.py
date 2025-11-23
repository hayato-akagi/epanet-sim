import streamlit as st
import pandas as pd
import plotly.express as px
import os

def render_metrics(exp_path):
    """メトリクスタブをレンダリング"""
    st.header("Performance Metrics")
    
    metrics_csv = os.path.join(exp_path, "metrics.csv")
    
    if not os.path.exists(metrics_csv):
        st.info("Metrics CSV not yet generated.")
        return
    
    m_df = pd.read_csv(metrics_csv)
    
    # ループIDによる分離
    if 'LoopID' in m_df.columns:
        render_multi_loop_metrics(m_df)
    else:
        render_single_loop_metrics(m_df)

def render_multi_loop_metrics(m_df):
    """複数ループのメトリクスを表示"""
    all_loop = m_df[m_df['LoopID'] == 'ALL']
    individual_loops = m_df[m_df['LoopID'] != 'ALL']
    
    # 全体統合指標
    if not all_loop.empty:
        st.subheader("Overall Performance")
        st.table(all_loop)
        
        row = all_loop.iloc[0]
        c1, c2, c3, c4, c5 = st.columns(5)
        
        if 'ControlMode' in row:
            c1.metric("Control Mode", row['ControlMode'].upper())
        if 'NumLoops' in row:
            c2.metric("Number of Loops", int(row['NumLoops']))
        if 'RMSE' in row:
            c3.metric("Avg RMSE", f"{row['RMSE']:.4f}")
        if 'MAE' in row:
            c4.metric("Avg MAE", f"{row['MAE']:.4f}")
        if 'MaxError' in row:
            c5.metric("Max Error", f"{row['MaxError']:.4f}")
    
    # 個別ループ性能
    if not individual_loops.empty:
        st.subheader("Individual Loop Performance")
        st.table(individual_loops)
        
        # ループごとの比較グラフ
        st.subheader("Loop Comparison")
        metrics_to_plot = ['MAE', 'RMSE', 'TotalVariation', 'SteadyMAE']
        available_metrics = [m for m in metrics_to_plot if m in individual_loops.columns]
        
        if available_metrics:
            fig_comp = px.bar(individual_loops, x='LoopID', y=available_metrics,
                             barmode='group', title="Performance Metrics by Loop")
            st.plotly_chart(fig_comp, use_container_width=True)

def render_single_loop_metrics(m_df):
    """単一ループのメトリクスを表示"""
    st.table(m_df)
    
    if m_df.empty:
        return
    
    row = m_df.iloc[0]
    
    # 1行目
    c1, c2, c3, c4, c5 = st.columns(5)
    
    if 'ControlMode' in row:
        c1.metric("Control Mode", row['ControlMode'].upper())
    if 'TargetValue' in row:
        c2.metric("Target Value", f"{row['TargetValue']:.2f}")
    if 'RMSE' in row:
        c3.metric("RMSE", f"{row['RMSE']:.4f}")
    if 'MAE' in row:
        c4.metric("MAE", f"{row['MAE']:.4f}")
    if 'MaxError' in row:
        c5.metric("Max Error", f"{row['MaxError']:.4f}")
    
    # 2行目
    c6, c7, c8, c9 = st.columns(4)
    
    if 'TotalVariation' in row:
        c6.metric("Valve TV", f"{row['TotalVariation']:.4f}")
    if 'SteadyMAE' in row:
        c7.metric("Steady MAE", f"{row['SteadyMAE']:.4f}")
    if 'MeanPressure' in row:
        c8.metric("Mean Pressure", f"{row['MeanPressure']:.2f}")
    if 'MeanFlow' in row:
        c9.metric("Mean Flow", f"{row['MeanFlow']:.2f}")