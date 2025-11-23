import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import os

from utils.constants import NETWORKS_DIR, COLOR_MAP, SYMBOL_MAP
from utils.inp_parser import parse_inp_geometry, parse_inp_details

def render_network_3d(exp_path, inp_filename, control_mode, control_loops, config_data):
    """3Dネットワーク可視化タブをレンダリング"""
    st.header(f"3D Network Visualization ({inp_filename})")
    inp_path = os.path.join(NETWORKS_DIR, inp_filename)
    
    # 複数ループの場合、制御対象ノードとアクチュエータを収集
    target_nodes = []
    actuator_links = []
    
    if control_loops:
        for loop in control_loops:
            target_nodes.append(loop.get('target', {}).get('node_id'))
            actuator_links.append(loop.get('actuator', {}).get('link_id'))
    else:
        target_nodes.append(config_data.get('target', {}).get('node_id', None))
        actuator_links.append(config_data.get('actuator', {}).get('link_id', None))
    
    sensor_type = f"{control_mode.capitalize()} Sensor"
    
    if not os.path.exists(inp_path):
        st.error(f"INP file not found at {inp_path}")
        return
    
    nodes, links = parse_inp_geometry(inp_path)
    
    if not nodes:
        st.warning("No coordinate data found in INP file.")
        return
    
    node_types, link_dict = parse_inp_details(inp_path)
    
    # ノードデータの準備
    node_data = prepare_node_data(nodes, node_types, target_nodes, sensor_type)
    node_df = pd.DataFrame(node_data)
    
    # 3Dプロット作成
    fig_3d = create_3d_plot(node_df, nodes, link_dict, actuator_links)
    
    st.plotly_chart(fig_3d, use_container_width=True)
    
    # 凡例説明
    display_legend(control_mode)
    
    # 制御構成の情報表示
    display_control_config(control_loops, target_nodes, actuator_links, sensor_type)

def prepare_node_data(nodes, node_types, target_nodes, sensor_type):
    """ノードデータを準備"""
    data_list = []
    
    for nid, coords in nodes.items():
        if 'x' not in coords or 'y' not in coords:
            continue
        
        node_type = node_types.get(nid, 'Unknown')
        is_sensor = (nid in target_nodes)
        
        if is_sensor:
            size = 20
            color = sensor_type
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
    
    return data_list

def create_3d_plot(node_df, nodes, link_dict, actuator_links):
    """3Dプロットを作成"""
    fig_3d = go.Figure()
    
    # ノードのプロット
    for node_type in COLOR_MAP.keys():
        type_nodes = node_df[node_df['Type'] == node_type]
        if not type_nodes.empty:
            fig_3d.add_trace(go.Scatter3d(
                x=type_nodes['X'],
                y=type_nodes['Y'],
                z=type_nodes['Z'],
                mode='markers+text',
                marker=dict(
                    size=type_nodes['Size'],
                    color=COLOR_MAP[node_type],
                    symbol=SYMBOL_MAP[node_type],
                    line=dict(width=2, color='white')
                ),
                text=type_nodes['ID'],
                textposition='top center',
                hovertext=type_nodes['Label'],
                hoverinfo='text',
                name=node_type,
                showlegend=True
            ))
    
    # アクチュエータ（制御バルブ）の描画
    for link_id, (n1, n2) in link_dict.items():
        if link_id in actuator_links:
            if n1 in nodes and n2 in nodes and 'x' in nodes[n1] and 'x' in nodes[n2]:
                fig_3d.add_trace(go.Scatter3d(
                    x=[nodes[n1]['x'], nodes[n2]['x']],
                    y=[nodes[n1]['y'], nodes[n2]['y']],
                    z=[nodes[n1]['z'], nodes[n2]['z']],
                    mode='lines',
                    line=dict(color='orange', width=8),
                    name=f'Valve {link_id} [ACTUATOR]',
                    hovertext=f"Control Valve: {link_id}",
                    hoverinfo='text',
                    showlegend=True
                ))
    
    # 通常のパイプを一括描画
    x_lines, y_lines, z_lines = [], [], []
    for link_id, (n1, n2) in link_dict.items():
        if link_id not in actuator_links:
            if n1 in nodes and n2 in nodes and 'x' in nodes[n1] and 'x' in nodes[n2]:
                x_lines.extend([nodes[n1]['x'], nodes[n2]['x'], None])
                y_lines.extend([nodes[n1]['y'], nodes[n2]['y'], None])
                z_lines.extend([nodes[n1]['z'], nodes[n2]['z'], None])
    
    if x_lines:
        fig_3d.add_trace(go.Scatter3d(
            x=x_lines, y=y_lines, z=z_lines,
            mode='lines',
            line=dict(color='lightgrey', width=2),
            name='Pipes',
            showlegend=True,
            hoverinfo='skip'
        ))
    
    fig_3d.update_layout(
        title=f"Network Topology with Control Points",
        scene=dict(
            xaxis_title="X Coordinate",
            yaxis_title="Y Coordinate",
            zaxis_title="Elevation (m)",
            aspectmode='data'
        ),
        height=700,
        legend=dict(
            yanchor="top", y=0.99,
            xanchor="left", x=0.01,
            bgcolor="rgba(255,255,255,0.8)"
        )
    )
    
    return fig_3d

def display_legend(control_mode):
    """凡例を表示"""
    if control_mode == 'pressure':
        sensor_emoji = "🔴"
        sensor_desc = "**Red Diamond**: Pressure Sensor"
    else:
        sensor_emoji = "🟣"
        sensor_desc = "**Purple Diamond**: Flow Sensor"
    
    st.markdown(f"""
    **Legend:**
    - {sensor_emoji} {sensor_desc}
    - 🟦 **Blue Square**: Reservoir
    - 🟦 **Cyan Square**: Tank
    - ⚪ **Gray Circle**: Junction
    - 🟧 **Orange Thick Line**: Control Valve
    - ⚪ **Gray Thin Line**: Regular Pipe
    """)

def display_control_config(control_loops, target_nodes, actuator_links, sensor_type):
    """制御構成を表示"""
    if len(control_loops) > 1:
        st.info(f"**Control Configuration:** {len(control_loops)} control loops detected")
        for i, loop in enumerate(control_loops):
            st.text(f"  Loop {loop.get('loop_id', i+1)}: Sensor at Node {loop.get('target', {}).get('node_id')}, Actuator at Link {loop.get('actuator', {}).get('link_id')}")
    elif target_nodes[0] or actuator_links[0]:
        st.info(f"**Control Configuration:** {sensor_type} at Node `{target_nodes[0]}`, Actuator at Link `{actuator_links[0]}`")