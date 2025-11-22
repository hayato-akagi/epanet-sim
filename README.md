# **Water Distribution Control System Simulation**

EPANETを用いた水理シミュレーションと、外部のPythonベースの制御ロジック（PID, MPC）を疎結合で連携させるシミュレーション基盤です。Podman Compose (Docker Compose) 上で動作し、リアルタイムに近い「Sense-Decide-Actuate」ループを再現します。

## **システム構成**

システムは以下の5つのコンテナサービスで構成されています。

1. **sim-runner**: EPANETシミュレータ実行エンジン。物理環境（プラント）の役割を果たします。  
2. **controller-pid**: PID制御アルゴリズムを提供するREST APIサーバー。  
3. **controller-mpc**: モデル予測制御（MPC）を提供するREST APIサーバー。  
4. **metrics-calculator**: 生成されたシミュレーション結果を監視し、制御性能指標（RMSE, MAE等）を自動計算するバックグラウンドサービス。  
5. **visualization**: Streamlitを用いた可視化ダッシュボード。3Dネットワーク図や時系列グラフを表示します。

### **アーキテクチャ図**

graph TD  
    subgraph "Simulation Environment"  
        SR\[sim-runner\] \--\>|Read| INP\[Net1.inp\]  
        SR \--\>|Write| RES\[result.csv\]  
    end

    subgraph "Controllers"  
        SR \-- HTTP POST (Sensor Data) \--\> PID\[controller-pid\]  
        SR \-- HTTP POST (Sensor Data) \--\> MPC\[controller-mpc\]  
        PID \-- JSON (Valve Setting) \--\> SR  
        MPC \-- JSON (Valve Setting) \--\> SR  
    end

    subgraph "Analysis & Viz"  
        MET\[metrics-calculator\] \-- Watch \--\> RES  
        MET \--\>|Generate| M\_CSV\[metrics.csv\]  
        VIZ\[visualization\] \-- Read \--\> RES  
        VIZ \-- Read \--\> M\_CSV  
    end

## **制御フロー (Control Loop)**

本システムは、タイムステップごとに以下のサイクルを繰り返します。

1. **Sense (観測)**:  
   * sim-runner が現在のシミュレーション時刻におけるセンサーデータ（特定のノードの圧力、リンクの流量）を取得します。  
2. **Decide Request (意思決定要求)**:  
   * sim-runner は、有効なコントローラ（PID または MPC）のAPIエンドポイントへHTTP POSTリクエストを送信します。  
   * ペイロードには「現在の圧力」「目標圧力」「前回のバルブ開度」が含まれます。  
3. **Control Calculation (制御計算)**:  
   * コントローラは受信したデータに基づき、次のタイムステップで適用すべき「バルブ開度 (0.0〜1.0)」を計算して返答します。  
4. **Actuate (操作)**:  
   * sim-runner は受け取ったバルブ開度をEPANETモデルに適用し、水理計算を1ステップ進めます。

## **クイックスタート**

### **前提条件**

* Podman Compose または Docker Compose  
* shared/networks/ ディレクトリに Net1.inp (EPANETサンプルファイル) が配置されていること。

### **1\. PID制御の実行 (デフォルト)**

\# デフォルトでは controller-pid が使用されます  
podman-compose up \--build

### **2\. MPC制御の実行**

環境変数を切り替えることで、接続先のコントローラと設定ファイルを変更します。

\# MPC用設定とコントローラホストを指定  
EXP\_CONFIG\_FILE=exp\_mpc.json \\  
EXP\_ID=exp\_mpc\_01 \\  
CONTROLLER\_HOST=controller-mpc \\  
podman-compose up \--build

### **3\. 結果の確認**

ブラウザで http://localhost:8501 にアクセスし、Visualizationダッシュボードを開きます。

## **設定ファイル詳細 (Configuration)**

実験設定は shared/configs/\*.json で管理されます。

### **基本構造 (simulation, network, target, actuator)**

全ての制御モードで共通の設定です。

| セクション | パラメータ | 説明 |
| :---- | :---- | :---- |
| **simulation** | duration | シミュレーション総時間（秒）。例: 86400 (24時間) |
|  | hydraulic\_step | 水理計算および制御のタイムステップ（秒）。例: 300 (5分) |
| **network** | inp\_file | 使用するEPANETネットワークファイル名。例: "Net1.inp" |
| **target** | node\_id | 制御目標とする観測ノードID。 |
|  | target\_pressure | 目標圧力値 (m)。 |
| **actuator** | link\_id | 操作対象となるバルブ（リンク）ID。 |
|  | initial\_setting | シミュレーション開始時のバルブ初期開度 (0.0〜1.0)。 |

### **PID制御用設定 (pid\_params)**

controller-pid を使用する場合に参照されます。

| パラメータ | 説明 |
| :---- | :---- |
| kp | **比例ゲイン**。現在の偏差に対する操作量の強さ。 |
| ki | **積分ゲイン**。過去の累積偏差に対する補正の強さ（定常偏差の除去）。 |
| kd | **微分ゲイン**。偏差の変化率に対する反応（オーバーシュート抑制）。 |
| setpoint | 目標値（通常は target.target\_pressure と同じ値に設定）。 |

**設定例:**

"pid\_params": {  
    "kp": 0.5,  
    "ki": 0.1,  
    "kd": 0.05,  
    "setpoint": 30.0  
}

### **MPC制御用設定 (mpc\_params)**

controller-mpc を使用する場合に参照されます。本システムでは、内部モデルとして「一次遅れ系 (First-Order Lag Process)」を仮定しています。

| パラメータ | 説明 |
| :---- | :---- |
| horizon | **予測ホライゾン**。何ステップ先まで予測して最適化するか。 |
| dt | 内部モデルで使用するタイムステップ（秒）。通常は hydraulic\_step と合わせます。 |
| tau | **時定数 (**$\\tau$**)**。システムが入力変化に対して63.2%応答するまでの時間（秒）。反応速度を表します。 |
| K | **プロセスゲイン (**$K$**)**。バルブ開度が1単位変化したとき、圧力がどれだけ変化するか（定常状態での比率）。 |
| weight\_error | 目的関数における「目標追従誤差」の重み。大きくすると追従性を重視します。 |
| weight\_du | 目的関数における「操作量変化 ($\\Delta u$)」の重み。大きくするとバルブの急激な動きを抑制します。 |

**設定例:**

"mpc\_params": {  
    "horizon": 10,  
    "dt": 300,  
    "tau": 1800.0,  
    "K": 50.0,  
    "weight\_error": 1.0,  
    "weight\_du": 10.0  
}

## **ディレクトリ構造**

* controller-pid/, controller-mpc/: 各制御ロジックのソースコード。  
* sim-runner/: EPANETシミュレーション実行エンジンのコード。  
* metrics/: 結果CSVを監視し、性能評価を行うコード。  
* visualization/: Streamlitダッシュボードのコード。  
* shared/: ホストとコンテナ間で共有されるデータ。  
  * configs/: 実験設定JSONファイル。  
  * networks/: EPANETモデルファイル (.inp)。  
  * results/: 実験IDごとの結果出力先。