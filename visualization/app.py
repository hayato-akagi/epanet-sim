import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
import json
import glob

# 定数・パス設定
RESULTS_DIR = os.environ.get('RESULTS_DIR', '/shared/results')
NETWORKS_DIR = os.environ.get('NETWORKS_DIR', '/shared/networks')

st.set_page_config(page_title="Water Control Viz", layout="wide")

st.title("Water Hydraulic Control Visualization")

# --- サイドバー: 実験の選択 ---
st.sidebar.header("Experiment Selection")

# 結果ディレクトリにある実験IDフォルダを取得
exp_dirs = [d for d in os.listdir(RESULTS_DIR) if os.path.isdir(os.path.join(RESULTS_DIR, d))]
exp_dirs.sort(reverse=True) # 新しい順

if not exp_dirs:
    st.warning("No experiment results found in shared/results.")
    st.stop()

selected_exp = st.sidebar.selectbox("Select Experiment ID", exp_dirs)
exp_path = os.path.join(RESULTS_DIR, selected_exp)

# --- 設定ファイルの読み込み ---
config_files = glob.glob(os.path.join(exp_path, "*_config.json"))
config_data = {}
inp_filename = "Net1.inp" # デフォルト

if config_files:
    with open(config_files[0], 'r') as f:
        config_data = json.load(f)
        st.sidebar.success(f"Loaded Config: {os.path.basename(config_files[0])}")
        # 使用されたネットワークファイルを特定
        inp_filename = config_data.get('network', {}).get('inp_file', 'Net1.inp')
else:
    st.sidebar.warning("Config file not found.")

# --- データ読み込み ---
result_csv = os.path.join(exp_path, "result.csv")
metrics_csv = os.path.join(exp_path, "metrics.csv")

if os.path.exists(result_csv):
    df = pd.read_csv(result_csv)
else:
    st.error(f"Result CSV not found in {exp_path}")
    st.stop()

# --- ヘルパー関数: INPファイルの簡易パース (3D用) ---
def parse_inp_geometry(inp_path):
    nodes = {} # id -> {x, y, z}
    links = [] # {source, target}
    
    current_section = None
    
    try:
        with open(inp_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('['):
                    current_section = line
                    continue
                if line.startswith(';') or not line:
                    continue
                
                parts = line.split()
                
                if current_section == "[COORDINATES]":
                    if len(parts) >= 3:
                        nid, x, y = parts[0], float(parts[1]), float(parts[2])
                        if nid not in nodes: nodes[nid] = {'z': 0} # デフォルト標高
                        nodes[nid]['x'] = x
                        nodes[nid]['y'] = y
                
                elif current_section in ["[JUNCTIONS]", "[RESERVOIRS]", "[TANKS]"]:
                    if len(parts) >= 2:
                        nid = parts[0]
                        elev = float(parts[1])
                        if nid not in nodes: nodes[nid] = {}
                        nodes[nid]['z'] = elev
                        
                elif current_section == "[PIPES]":
                    if len(parts) >= 3:
                        # ID, Node1, Node2
                        links.append((parts[1], parts[2]))
                        
        return nodes, links
    except Exception as e:
        st.error(f"Error parsing INP file: {e}")
        return {}, []

# --- タブ構成 ---
tab1, tab2, tab3, tab4 = st.tabs(["3D Network", "Control Performance", "Time Series Analysis", "Metrics"])

# === Tab 1: 3D Network ===
with tab1:
    st.header(f"3D Network Visualization ({inp_filename})")
    inp_path = os.path.join(NETWORKS_DIR, inp_filename)
    
    if os.path.exists(inp_path):
        nodes, links = parse_inp_geometry(inp_path)
        
        if nodes:
            # ノードデータのDataFrame化
            node_df = pd.DataFrame.from_dict(nodes, orient='index').reset_index()
            node_df.columns = ['ID', 'Z', 'X', 'Y'] 
            
            data_list = []
            for nid, coords in nodes.items():
                if 'x' in coords and 'y' in coords:
                    data_list.append({'ID': nid, 'X': coords['x'], 'Y': coords['y'], 'Z': coords.get('z', 0)})
            node_df = pd.DataFrame(data_list)

            # Plotly 3D Scatter
            fig_3d = px.scatter_3d(
                node_df, x='X', y='Y', z='Z', 
                text='ID', 
                color='Z',
                color_continuous_scale='Viridis',
                title="Network Topology (X, Y, Elevation)"
            )
            
            # リンク（パイプ）の追加
            x_lines = []
            y_lines = []
            z_lines = []
            for n1, n2 in links:
                if n1 in nodes and n2 in nodes and 'x' in nodes[n1] and 'x' in nodes[n2]:
                    x_lines.extend([nodes[n1]['x'], nodes[n2]['x'], None])
                    y_lines.extend([nodes[n1]['y'], nodes[n2]['y'], None])
                    z_lines.extend([nodes[n1]['z'], nodes[n2]['z'], None])
            
            fig_3d.add_trace(go.Scatter3d(
                x=x_lines, y=y_lines, z=z_lines,
                mode='lines',
                line=dict(color='lightgrey', width=2),
                name='Pipes'
            ))
            
            fig_3d.update_layout(height=700)
            st.plotly_chart(fig_3d, use_container_width=True)
        else:
            st.warning("No coordinate data found in INP file.")
    else:
        st.error(f"INP file not found at {inp_path}")

# === Tab 2: Control Performance ===
with tab2:
    st.header("Control Loop Performance")
    
    col1, col2 = st.columns(2)
    
    # 圧力追従グラフ
    with col1:
        fig_p = go.Figure()
        fig_p.add_trace(go.Scatter(x=df['Time'], y=df['TargetPressure'], name='Target', line=dict(dash='dash', color='red')))
        fig_p.add_trace(go.Scatter(x=df['Time'], y=df['Pressure'], name='Measured', line=dict(color='blue')))
        fig_p.update_layout(title="Pressure Tracking", xaxis_title="Time (s)", yaxis_title="Pressure (m)")
        st.plotly_chart(fig_p, use_container_width=True)
        
    # バルブ操作量
    with col2:
        fig_v = px.line(df, x='Time', y=['ValveSetting', 'NewValveSetting'], title="Valve Actuation")
        st.plotly_chart(fig_v, use_container_width=True)

    # コントローラ内部状態の可視化 (汎用化)
    st.subheader("Controller Internal States")
    
    # 特定のカラム（PIDなど）をチェックし、データが存在する場合のみ表示する
    potential_cols = ['PID_P', 'PID_I', 'PID_D']
    active_cols = []
    
    for col in potential_cols:
        if col in df.columns:
            # すべて0（MPCなどの場合）であれば表示しない
            if df[col].abs().sum() > 1e-6:
                active_cols.append(col)
    
    if active_cols:
        fig_internal = px.line(df, x='Time', y=active_cols, title="Controller Internal Components")
        st.plotly_chart(fig_internal, use_container_width=True)
    else:
        st.info("No active internal state variables detected (e.g., PID terms are zero or not logged).")

# === Tab 3: Time Series Analysis ===
with tab3:
    st.header("Full Time Series Data")
    cols = st.multiselect("Select Columns to Plot", df.columns, default=['Pressure', 'Flow'])
    
    if cols:
        fig_ts = px.line(df, x='Time', y=cols, title="Custom Time Series Plot")
        st.plotly_chart(fig_ts, use_container_width=True)
        
    st.subheader("Raw Data")
    st.dataframe(df)

# === Tab 4: Metrics ===
with tab4:
    st.header("Performance Metrics")
    if os.path.exists(metrics_csv):
        m_df = pd.read_csv(metrics_csv)
        st.table(m_df)
        
        if not m_df.empty:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("RMSE", f"{m_df.iloc[0]['RMSE']:.4f}")
            c2.metric("MAE", f"{m_df.iloc[0]['MAE']:.4f}")
            c3.metric("Valve TV", f"{m_df.iloc[0]['TotalVariation']:.4f}")
            c4.metric("Max Error", f"{m_df.iloc[0]['MaxError']:.4f}")
    else:
        st.info("Metrics CSV not yet generated.")