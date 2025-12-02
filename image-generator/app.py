import os
import redis
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyBboxPatch
from flask import Flask, request, jsonify
from PIL import Image
import io

app = Flask(__name__)

REDIS_URL = os.environ.get('REDIS_URL', 'redis://redis:6379')
redis_client = redis.from_url(REDIS_URL, decode_responses=False)

# EPANETネットワークの簡易トポロジ（Net1.inp）
NETWORK_NODES = {
    '2': (0, 0),
    '10': (-1, 1),
    '11': (1, 1),
    '12': (0, 2),
    '13': (-1, 3),
    '21': (1, 3),
    '22': (0, 4),
    '23': (-1, 5),
    '31': (1, 5),
    '32': (0, 6),
    '9': (0, -1)
}

NETWORK_LINKS = [
    ('9', '2'), ('2', '12'), ('12', '22'), ('22', '32'),
    ('2', '10'), ('10', '13'), ('13', '23'),
    ('2', '11'), ('11', '21'), ('21', '31')
]

def generate_system_ui(state, size=(256, 256)):
    """ネットワークトポロジ + 圧力ヒートマップ"""
    fig, ax = plt.subplots(figsize=(2.56, 2.56), dpi=100)
    
    # ノードの圧力値（実際は全ノードの圧力が必要だが簡略化）
    pressure = state.get('pressure', 30.0)
    target = state.get('target_pressure', 30.0)
    
    # ノードをプロット
    for node_id, (x, y) in NETWORK_NODES.items():
        # 圧力で色分け（簡易版: 制御ノードのみ実際の値）
        if node_id == '2':
            color_val = (pressure - 20) / 30  # 20-50mの範囲を0-1に正規化
        else:
            color_val = 0.5
        
        color = plt.cm.viridis(np.clip(color_val, 0, 1))
        
        circle = Circle((x, y), 0.3, color=color, ec='black', linewidth=1.5)
        ax.add_patch(circle)
        
        # ノードIDを表示
        ax.text(x, y, node_id, ha='center', va='center', fontsize=6, color='white', weight='bold')
    
    # 制御対象ノードを強調
    highlight = Circle((0, 0), 0.35, fill=False, ec='red', linewidth=2)
    ax.add_patch(highlight)
    
    # リンクを描画
    for start, end in NETWORK_LINKS:
        x_start, y_start = NETWORK_NODES[start]
        x_end, y_end = NETWORK_NODES[end]
        ax.plot([x_start, x_end], [y_start, y_end], 'k-', linewidth=1, alpha=0.5)
    
    ax.set_xlim(-2, 2)
    ax.set_ylim(-2, 7)
    ax.set_aspect('equal')
    ax.axis('off')
    ax.set_title(f'Network - P={pressure:.1f}m (Target={target:.1f}m)', fontsize=8)
    
    # カラーバー
    sm = plt.cm.ScalarMappable(cmap=plt.cm.viridis, norm=plt.Normalize(vmin=20, vmax=50))
    cbar = plt.colorbar(sm, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label('Pressure (m)', fontsize=6)
    cbar.ax.tick_params(labelsize=6)
    
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', bbox_inches='tight', dpi=100)
    plt.close(fig)
    
    return buffer.getvalue()

def generate_valve_detail(state, size=(256, 256)):
    """バルブ開度のゲージチャート"""
    fig, ax = plt.subplots(figsize=(2.56, 2.56), dpi=100)
    
    valve = state.get('valve_setting', 0.5) * 100
    upstream_p = state.get('upstream_pressure', 50.0)
    downstream_p = state.get('downstream_pressure', 30.0)
    delta_p = upstream_p - downstream_p
    
    # ゲージチャート（半円）
    theta = np.linspace(0, np.pi, 100)
    
    # 背景
    ax.fill_between(theta, 0, 1, color='lightgray', alpha=0.3, transform=ax.transData)
    
    # 現在値
    valve_theta = np.pi * (1 - valve / 100)
    ax.plot([np.pi/2, np.pi/2 + 0.8*np.cos(valve_theta)], 
            [0, 0.8*np.sin(valve_theta)], 'r-', linewidth=4)
    
    # ゲージの目盛り
    for v in [0, 25, 50, 75, 100]:
        t = np.pi * (1 - v / 100)
        ax.plot([np.pi/2 + 0.9*np.cos(t), np.pi/2 + 1.0*np.cos(t)], 
                [0.9*np.sin(t), 1.0*np.sin(t)], 'k-', linewidth=1)
        ax.text(np.pi/2 + 1.1*np.cos(t), 1.1*np.sin(t), f'{v}%', 
                ha='center', va='center', fontsize=8)
    
    # 数値表示
    ax.text(np.pi/2, -0.3, f'{valve:.1f}%', ha='center', va='top', fontsize=24, weight='bold')
    ax.text(np.pi/2, -0.5, f'ΔP = {delta_p:.1f}m', ha='center', va='top', fontsize=12)
    
    ax.set_xlim(0, np.pi)
    ax.set_ylim(-0.6, 1.2)
    ax.set_aspect('equal')
    ax.axis('off')
    ax.set_title('Valve Opening', fontsize=10, weight='bold')
    
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', bbox_inches='tight', dpi=100)
    plt.close(fig)
    
    return buffer.getvalue()

def generate_flow_dashboard(state, history, size=(256, 256)):
    """流量の時系列グラフ"""
    fig, ax = plt.subplots(figsize=(2.56, 2.56), dpi=100)
    
    # 履歴データ
    flow_history = history.get('flow', [])
    if not flow_history:
        flow_history = [state.get('flow', 95.0)]
    
    steps = list(range(len(flow_history)))
    target_flow = state.get('target_flow', 100.0)
    
    # プロット
    ax.plot(steps, flow_history, 'r-', linewidth=2, label='Actual Flow')
    ax.axhline(target_flow, color='g', linestyle='--', linewidth=1.5, label='Target')
    
    # 許容範囲（±5%）
    ax.fill_between(steps, 
                     target_flow * 0.95, 
                     target_flow * 1.05, 
                     color='gray', alpha=0.2, label='±5% Range')
    
    ax.set_xlabel('Step', fontsize=8)
    ax.set_ylabel('Flow (L/s)', fontsize=8)
    ax.set_title('Flow History', fontsize=10, weight='bold')
    ax.legend(fontsize=6, loc='upper right')
    ax.grid(True, alpha=0.3)
    ax.tick_params(labelsize=7)
    
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', bbox_inches='tight', dpi=100)
    plt.close(fig)
    
    return buffer.getvalue()

def generate_comparison(state, prev_state, size=(256, 256)):
    """前ステップとの比較"""
    fig, axes = plt.subplots(1, 2, figsize=(5.12, 2.56), dpi=100)
    
    pressure = state.get('pressure', 30.0)
    prev_pressure = prev_state.get('pressure', 29.5) if prev_state else pressure
    
    valve = state.get('valve_setting', 0.5) * 100
    prev_valve = prev_state.get('valve_setting', 0.48) * 100 if prev_state else valve
    
    # 左: 前ステップ
    axes[0].text(0.5, 0.7, 'Previous', ha='center', va='center', fontsize=12, weight='bold', transform=axes[0].transAxes)
    axes[0].text(0.5, 0.5, f'P: {prev_pressure:.1f}m', ha='center', va='center', fontsize=10, transform=axes[0].transAxes)
    axes[0].text(0.5, 0.3, f'V: {prev_valve:.1f}%', ha='center', va='center', fontsize=10, transform=axes[0].transAxes)
    axes[0].axis('off')
    
    # 右: 現在
    axes[1].text(0.5, 0.7, 'Current', ha='center', va='center', fontsize=12, weight='bold', transform=axes[1].transAxes)
    axes[1].text(0.5, 0.5, f'P: {pressure:.1f}m', ha='center', va='center', fontsize=10, transform=axes[1].transAxes)
    axes[1].text(0.5, 0.3, f'V: {valve:.1f}%', ha='center', va='center', fontsize=10, transform=axes[1].transAxes)
    axes[1].axis('off')
    
    # 中央に変化量
    fig.text(0.5, 0.1, f'ΔP: {pressure - prev_pressure:+.2f}m, ΔV: {valve - prev_valve:+.1f}%', 
             ha='center', fontsize=10, weight='bold')
    
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', bbox_inches='tight', dpi=50)  # 横長なのでdpi調整
    plt.close(fig)
    
    return buffer.getvalue()

# グローバルに前ステップの状態を保存
prev_states = {}

@app.route('/generate', methods=['POST'])
def generate():
    """画像生成エンドポイント"""
    data = request.json
    
    exp_id = data.get('exp_id', 'unknown')
    step = data.get('step', 0)
    state = data.get('state', {})
    history = data.get('history', {})
    
    # 前ステップの状態を取得
    prev_state = prev_states.get(exp_id)
    
    # 4種類の画像を生成
    images = {
        'system_ui': generate_system_ui(state),
        'valve_detail': generate_valve_detail(state),
        'flow_dashboard': generate_flow_dashboard(state, history),
        'comparison': generate_comparison(state, prev_state)
    }
    
    # 現在の状態を保存
    prev_states[exp_id] = state
    
    # Redisに保存
    redis_keys = {}
    for key, img_bytes in images.items():
        redis_key = f"{exp_id}:step_{step}:{key}"
        redis_client.setex(redis_key, 300, img_bytes)
        redis_keys[key] = redis_key
    
    print(f"[image-generator] Generated images for {exp_id}, step {step}")
    
    return jsonify({
        "redis_keys": redis_keys,
        "metadata": {
            "generated_at": data.get('state', {}).get('timestamp', 'unknown'),
            "image_size": [256, 256]
        }
    })

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)