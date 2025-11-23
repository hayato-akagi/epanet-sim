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
control_mode = "pressure" # デフォルト

if config_files:
    with open(config_files[0], 'r') as f:
        config_data = json.load(f)
        st.sidebar.success(f"Loaded Config: {os.path.basename(config_files[0])}")
        # 使用されたネットワークファイルを特定
        inp_filename = config_data.get('network', {}).get('inp_file', 'Net1.inp')
        control_mode = config_data.get('control_mode', 'pressure')
else:
    st.sidebar.warning("Config file not found.")

# --- データ読み込み ---
result_csv = os.path.join(exp_path, "result.csv")
metrics_csv = os.path.join(exp_path, "metrics.csv")

if os.path.exists(result_csv):
    df = pd.read_csv(result_csv)
    
    # CSVから制御モードを取得（設定ファイルがない場合）
    if 'ControlMode' in df.columns:
        control_mode = df['ControlMode'].iloc[0]
else:
    st.error(f"Result CSV not found in {exp_path}")
    st.stop()

# 制御モード表示
st.sidebar.info(f"**Control Mode:** {control_mode.upper()}")

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
    
    # 設定から制御対象のノードとアクチュエータを取得
    target_node_id = config_data.get('target', {}).get('node_id', None)
    actuator_link_id = config_data.get('actuator', {}).get('link_id', None)
    
    # センサータイプの判定（制御モードから）
    sensor_type = f"{control_mode.capitalize()} Sensor"
    
    if os.path.exists(inp_path):
        nodes, links = parse_inp_geometry(inp_path)
        
        if nodes:
            # ノードタイプの判定（INPファイルから）
            node_types = {}  # node_id -> type
            link_dict = {}  # link_id -> (node1, node2)
            
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
                        
                        if current_section == "[JUNCTIONS]" and len(parts) >= 2:
                            node_types[parts[0]] = 'Junction'
                        elif current_section == "[RESERVOIRS]" and len(parts) >= 2:
                            node_types[parts[0]] = 'Reservoir'
                        elif current_section == "[TANKS]" and len(parts) >= 2:
                            node_types[parts[0]] = 'Tank'
                        elif current_section == "[PIPES]" and len(parts) >= 3:
                            link_dict[parts[0]] = (parts[1], parts[2])
                        elif current_section == "[VALVES]" and len(parts) >= 3:
                            link_dict[parts[0]] = (parts[1], parts[2])
            except Exception as e:
                st.warning(f"Could not parse node types: {e}")
            
            # ノードデータの準備
            data_list = []
            for nid, coords in nodes.items():
                if 'x' in coords and 'y' in coords:
                    # ノードの役割を判定
                    node_type = node_types.get(nid, 'Unknown')
                    
                    # センサーノードかどうか
                    is_sensor = (nid == target_node_id)
                    
                    # サイズと色を決定
                    if is_sensor:
                        size = 20
                        color = sensor_type  # "Pressure Sensor" or "Flow Sensor"
                        symbol = 'diamond'
                    elif node_type == 'Reservoir':
                        size = 15
                        color = 'Reservoir'
                        symbol = 'square'
                    elif node_type == 'Tank':
                        size = 15
                        color = 'Tank'
                        symbol = 'square'
                    else:
                        size = 8
                        color = 'Junction'
                        symbol = 'circle'
                    
                    data_list.append({
                        'ID': nid,
                        'X': coords['x'],
                        'Y': coords['y'],
                        'Z': coords.get('z', 0),
                        'Type': color,
                        'Size': size,
                        'Symbol': symbol,
                        'Label': f"{nid} ({node_type})" + (f" [{sensor_type.upper()}]" if is_sensor else "")
                    })
            
            node_df = pd.DataFrame(data_list)
            
            # 3Dプロット作成
            fig_3d = go.Figure()
            
            # ノードタイプごとにトレースを分けて色分け
            color_map = {
                'Pressure Sensor': 'red',
                'Flow Sensor': 'purple',
                'Reservoir': 'blue',
                'Tank': 'cyan',
                'Junction': 'lightgray'
            }
            
            symbol_map = {
                'Pressure Sensor': 'diamond',
                'Flow Sensor': 'diamond',
                'Reservoir': 'square',
                'Tank': 'square',
                'Junction': 'circle'
            }
            
            for node_type in color_map.keys():
                type_nodes = node_df[node_df['Type'] == node_type]
                if not type_nodes.empty:
                    fig_3d.add_trace(go.Scatter3d(
                        x=type_nodes['X'],
                        y=type_nodes['Y'],
                        z=type_nodes['Z'],
                        mode='markers+text',
                        marker=dict(
                            size=type_nodes['Size'],
                            color=color_map[node_type],
                            symbol=symbol_map[node_type],
                            line=dict(width=2, color='white')
                        ),
                        text=type_nodes['ID'],
                        textposition='top center',
                        hovertext=type_nodes['Label'],
                        hoverinfo='text',
                        name=node_type,
                        showlegend=True
                    ))
            
            # パイプの描画（通常のパイプとバルブを区別）
            for link_id, (n1, n2) in link_dict.items():
                if n1 in nodes and n2 in nodes and 'x' in nodes[n1] and 'x' in nodes[n2]:
                    is_actuator = (link_id == actuator_link_id)
                    
                    x_coords = [nodes[n1]['x'], nodes[n2]['x']]
                    y_coords = [nodes[n1]['y'], nodes[n2]['y']]
                    z_coords = [nodes[n1]['z'], nodes[n2]['z']]
                    
                    if is_actuator:
                        # アクチュエータ（制御バルブ）を強調表示
                        fig_3d.add_trace(go.Scatter3d(
                            x=x_coords,
                            y=y_coords,
                            z=z_coords,
                            mode='lines',
                            line=dict(color='orange', width=8),
                            name=f'Valve {link_id} [ACTUATOR]',
                            hovertext=f"Control Valve: {link_id}",
                            hoverinfo='text',
                            showlegend=True
                        ))
                    else:
                        # 通常のパイプ（まとめて1つのトレースにする）
                        continue
            
            # 通常のパイプを一括描画
            x_lines = []
            y_lines = []
            z_lines = []
            for link_id, (n1, n2) in link_dict.items():
                if link_id != actuator_link_id:
                    if n1 in nodes and n2 in nodes and 'x' in nodes[n1] and 'x' in nodes[n2]:
                        x_lines.extend([nodes[n1]['x'], nodes[n2]['x'], None])
                        y_lines.extend([nodes[n1]['y'], nodes[n2]['y'], None])
                        z_lines.extend([nodes[n1]['z'], nodes[n2]['z'], None])
            
            if x_lines:
                fig_3d.add_trace(go.Scatter3d(
                    x=x_lines,
                    y=y_lines,
                    z=z_lines,
                    mode='lines',
                    line=dict(color='lightgrey', width=2),
                    name='Pipes',
                    showlegend=True,
                    hoverinfo='skip'
                ))
            
            fig_3d.update_layout(
                title=f"Network Topology with Control Points ({control_mode.upper()} Control)",
                scene=dict(
                    xaxis_title="X Coordinate",
                    yaxis_title="Y Coordinate",
                    zaxis_title="Elevation (m)",
                    aspectmode='data'
                ),
                height=700,
                legend=dict(
                    yanchor="top",
                    y=0.99,
                    xanchor="left",
                    x=0.01,
                    bgcolor="rgba(255,255,255,0.8)"
                )
            )
            
            st.plotly_chart(fig_3d, use_container_width=True)
            
            # 凡例説明（制御モードに応じて動的に変更）
            if control_mode == 'pressure':
                sensor_emoji = "🔴"
                sensor_desc = "**Red Diamond**: Pressure Sensor (measurement node)"
            else:
                sensor_emoji = "🟣"
                sensor_desc = "**Purple Diamond**: Flow Sensor (measurement node)"
            
            st.markdown(f"""
            **Legend:**
            - {sensor_emoji} {sensor_desc}
            - 🟦 **Blue Square**: Reservoir (water source)
            - 🟦 **Cyan Square**: Tank (storage)
            - ⚪ **Gray Circle**: Junction (pipe connection)
            - 🟧 **Orange Thick Line**: Control Valve (actuator)
            - ⚪ **Gray Thin Line**: Regular Pipe
            """)
            
            # 制御構成の情報表示
            if target_node_id or actuator_link_id:
                st.info(f"**Control Configuration:** {sensor_type} at Node `{target_node_id}`, Actuator at Link `{actuator_link_id}`")
        else:
            st.warning("No coordinate data found in INP file.")
    else:
        st.error(f"INP file not found at {inp_path}")

# === Tab 2: Control Performance ===
with tab2:
    st.header("Control Loop Performance")
    
    # 制御対象値とターゲット値の取得
    if 'ControlledValue' in df.columns and 'TargetValue' in df.columns:
        controlled_col = 'ControlledValue'
        target_col = 'TargetValue'
        ylabel = f"{control_mode.capitalize()} ({'m' if control_mode == 'pressure' else 'm³/h'})"
    else:
        # 旧形式対応
        if control_mode == 'flow':
            controlled_col = 'Flow'
            target_col = 'TargetFlow'
            ylabel = "Flow (m³/h)"
        else:
            controlled_col = 'Pressure'
            target_col = 'TargetPressure'
            ylabel = "Pressure (m)"
    
    col1, col2 = st.columns(2)
    
    # 制御対象値の追従グラフ
    with col1:
        fig_ctrl = go.Figure()
        fig_ctrl.add_trace(go.Scatter(
            x=df['Time'], 
            y=df[target_col], 
            name='Target', 
            line=dict(dash='dash', color='red')
        ))
        fig_ctrl.add_trace(go.Scatter(
            x=df['Time'], 
            y=df[controlled_col], 
            name='Measured', 
            line=dict(color='blue')
        ))
        fig_ctrl.update_layout(
            title=f"{control_mode.capitalize()} Tracking",
            xaxis_title="Time (s)",
            yaxis_title=ylabel
        )
        st.plotly_chart(fig_ctrl, use_container_width=True)
        
    # バルブ操作量
    with col2:
        fig_v = px.line(df, x='Time', y=['ValveSetting', 'NewValveSetting'], title="Valve Actuation")
        st.plotly_chart(fig_v, use_container_width=True)

    # 圧力と流量の両方を表示（参考情報）
    st.subheader("System State (Pressure & Flow)")
    col3, col4 = st.columns(2)
    
    with col3:
        if 'Pressure' in df.columns:
            fig_p = px.line(df, x='Time', y='Pressure', title="Pressure Over Time")
            fig_p.update_layout(yaxis_title="Pressure (m)")
            st.plotly_chart(fig_p, use_container_width=True)
    
    with col4:
        if 'Flow' in df.columns:
            fig_f = px.line(df, x='Time', y='Flow', title="Flow Over Time")
            fig_f.update_layout(yaxis_title="Flow (m³/h)")
            st.plotly_chart(fig_f, use_container_width=True)

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
    
    # 誤差の可視化
    if 'Error' in df.columns:
        st.subheader("Control Error")
        fig_error = px.line(df, x='Time', y='Error', title="Control Error Over Time")
        fig_error.update_layout(yaxis_title="Error")
        st.plotly_chart(fig_error, use_container_width=True)

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
            # メトリクスの動的表示（制御モードに応じて）
            row = m_df.iloc[0]
            
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
    else:
        st.info("Metrics CSV not yet generated.")