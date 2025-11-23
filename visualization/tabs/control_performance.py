import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

def render_control_performance(df, control_mode, has_multiple_loops, loop_ids):
    """制御性能タブをレンダリング"""
    st.header("Control Loop Performance")
    
    # ループ選択
    if has_multiple_loops:
        selected_loop = st.selectbox("Select Loop", ['All Loops'] + list(loop_ids))
        df_display = df if selected_loop == 'All Loops' else df[df['LoopID'] == selected_loop].copy()
    else:
        df_display = df.copy()
        selected_loop = 'default'
    
    # 制御対象値とターゲット値の列を特定
    controlled_col, target_col, ylabel = get_control_columns(df_display, control_mode)
    
    # メイングラフ
    col1, col2 = st.columns(2)
    
    with col1:
        plot_tracking_graph(df, df_display, controlled_col, target_col, ylabel, 
                           has_multiple_loops, selected_loop, loop_ids, control_mode)
    
    with col2:
        plot_valve_actuation(df, df_display, has_multiple_loops, selected_loop, loop_ids)
    
    # システム状態
    st.subheader("System State (Pressure & Flow)")
    col3, col4 = st.columns(2)
    
    with col3:
        plot_pressure(df_display, has_multiple_loops, selected_loop)
    
    with col4:
        plot_flow(df_display, has_multiple_loops, selected_loop)
    
    # コントローラ内部状態
    plot_controller_internals(df_display, has_multiple_loops, selected_loop)
    
    # 誤差
    plot_error(df_display, has_multiple_loops, selected_loop)

def get_control_columns(df, control_mode):
    """制御対象値とターゲット値の列名を取得"""
    if 'ControlledValue' in df.columns and 'TargetValue' in df.columns:
        controlled_col = 'ControlledValue'
        target_col = 'TargetValue'
        ylabel = f"{control_mode.capitalize()} ({'m' if control_mode == 'pressure' else 'm³/h'})"
    else:
        if control_mode == 'flow':
            controlled_col = 'Flow'
            target_col = 'TargetFlow'
            ylabel = "Flow (m³/h)"
        else:
            controlled_col = 'Pressure'
            target_col = 'TargetPressure'
            ylabel = "Pressure (m)"
    
    return controlled_col, target_col, ylabel

def plot_tracking_graph(df, df_display, controlled_col, target_col, ylabel,
                        has_multiple_loops, selected_loop, loop_ids, control_mode):
    """追従グラフを描画"""
    fig_ctrl = go.Figure()
    
    if has_multiple_loops and selected_loop == 'All Loops':
        for loop_id in loop_ids:
            df_loop = df[df['LoopID'] == loop_id]
            fig_ctrl.add_trace(go.Scatter(
                x=df_loop['Time'], y=df_loop[target_col],
                name=f'{loop_id} Target',
                line=dict(dash='dash'),
                legendgroup=loop_id
            ))
            fig_ctrl.add_trace(go.Scatter(
                x=df_loop['Time'], y=df_loop[controlled_col],
                name=f'{loop_id} Measured',
                legendgroup=loop_id
            ))
    else:
        fig_ctrl.add_trace(go.Scatter(
            x=df_display['Time'], y=df_display[target_col],
            name='Target', line=dict(dash='dash', color='red')
        ))
        fig_ctrl.add_trace(go.Scatter(
            x=df_display['Time'], y=df_display[controlled_col],
            name='Measured', line=dict(color='blue')
        ))
    
    fig_ctrl.update_layout(
        title=f"{control_mode.capitalize()} Tracking",
        xaxis_title="Time (s)", yaxis_title=ylabel
    )
    st.plotly_chart(fig_ctrl, use_container_width=True)

def plot_valve_actuation(df, df_display, has_multiple_loops, selected_loop, loop_ids):
    """バルブ操作量を描画"""
    if has_multiple_loops and selected_loop == 'All Loops':
        fig_v = go.Figure()
        for loop_id in loop_ids:
            df_loop = df[df['LoopID'] == loop_id]
            fig_v.add_trace(go.Scatter(
                x=df_loop['Time'], y=df_loop['NewValveSetting'],
                name=f'{loop_id} Valve', mode='lines'
            ))
        fig_v.update_layout(title="Valve Actuation (All Loops)")
        st.plotly_chart(fig_v, use_container_width=True)
    else:
        fig_v = px.line(df_display, x='Time', y=['ValveSetting', 'NewValveSetting'], 
                       title="Valve Actuation")
        st.plotly_chart(fig_v, use_container_width=True)

def plot_pressure(df_display, has_multiple_loops, selected_loop):
    """圧力グラフを描画"""
    if 'Pressure' in df_display.columns:
        fig_p = px.line(df_display, x='Time', y='Pressure',
                       color='LoopID' if has_multiple_loops and selected_loop == 'All Loops' else None,
                       title="Pressure Over Time")
        fig_p.update_layout(yaxis_title="Pressure (m)")
        st.plotly_chart(fig_p, use_container_width=True)

def plot_flow(df_display, has_multiple_loops, selected_loop):
    """流量グラフを描画"""
    if 'Flow' in df_display.columns:
        fig_f = px.line(df_display, x='Time', y='Flow',
                       color='LoopID' if has_multiple_loops and selected_loop == 'All Loops' else None,
                       title="Flow Over Time")
        fig_f.update_layout(yaxis_title="Flow (m³/h)")
        st.plotly_chart(fig_f, use_container_width=True)

def plot_controller_internals(df_display, has_multiple_loops, selected_loop):
    """コントローラ内部状態を描画"""
    st.subheader("Controller Internal States")
    
    potential_cols = ['PID_P', 'PID_I', 'PID_D']
    active_cols = [col for col in potential_cols if col in df_display.columns and df_display[col].abs().sum() > 1e-6]
    
    if active_cols:
        fig_internal = px.line(df_display, x='Time', y=active_cols,
                              color='LoopID' if has_multiple_loops and selected_loop == 'All Loops' else None,
                              title="Controller Internal Components")
        st.plotly_chart(fig_internal, use_container_width=True)
    else:
        st.info("No active internal state variables detected.")

def plot_error(df_display, has_multiple_loops, selected_loop):
    """誤差グラフを描画"""
    if 'Error' in df_display.columns:
        st.subheader("Control Error")
        fig_error = px.line(df_display, x='Time', y='Error',
                           color='LoopID' if has_multiple_loops and selected_loop == 'All Loops' else None,
                           title="Control Error Over Time")
        fig_error.update_layout(yaxis_title="Error")
        st.plotly_chart(fig_error, use_container_width=True)