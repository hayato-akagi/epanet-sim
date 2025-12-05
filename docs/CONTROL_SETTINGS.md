# EPANET制御設定ガイド

## 圧力制御

### Net1

**ノード**: `2` (タンク出口付近のジャンクション)
**アクチュエータ**: `10` (PRV - Pressure Reducing Valve)
**目標値**: 30.0 m
**PIDパラメータ**: Kp=0.01, Ki=0.0001, Kd=0.005

**設定例**:
```json
{
  "control_mode": "pressure",
  "network": {"inp_file": "Net1.inp"},
  "control_loops": [{
    "loop_id": "loop_1",
    "target": {"node_id": "2", "target_pressure": 30.0},
    "actuator": {"link_id": "10", "initial_setting": 0.5},
    "pid_params": {"Kp": 0.01, "Ki": 0.0001, "Kd": 0.005}
  }]
}
```

**引用論文**:
- EPANET 2.2 User Manual (EPA, 2020)
- Rossman, L.A. (2000). EPANET 2 Users Manual

---

### Net2

**ノード**: 
- `11` (中心部ジャンクション、センサー設置地点)
- `19` (別ゾーンジャンクション、センサー設置地点)

**アクチュエータ**: 
- `25` (PRV - Zone 1)
- `30` (PRV - Zone 2)

**目標値**: 
- ノード11: 25.0 m
- ノード19: 28.0 m

**PIDパラメータ**: Kp=0.008, Ki=0.00008, Kd=0.004

**設定例**:
```json
{
  "control_mode": "pressure",
  "network": {"inp_file": "Net2.inp"},
  "control_loops": [
    {
      "loop_id": "loop_1",
      "target": {"node_id": "11", "target_pressure": 25.0},
      "actuator": {"link_id": "25", "initial_setting": 0.6},
      "pid_params": {"Kp": 0.008, "Ki": 0.00008, "Kd": 0.004}
    },
    {
      "loop_id": "loop_2",
      "target": {"node_id": "19", "target_pressure": 28.0},
      "actuator": {"link_id": "30", "initial_setting": 0.5},
      "pid_params": {"Kp": 0.008, "Ki": 0.00008, "Kd": 0.004}
    }
  ]
}
```

**引用論文**:
- EPANET 2.2 User Manual, Example 2 (Tracer Study)
- EPyT Documentation - Net2 Examples

---

### Net3

**ノード**: 
- `161` (高需要エリア)
- `65` (中需要エリア)
- `45` (高地エリア)

**アクチュエータ**: 
- `155` (PRV - Zone 1)
- `70` (PRV - Zone 2)
- `50` (PRV - Zone 3)

**目標値**: 
- ノード161: 30.0 m
- ノード65: 28.0 m
- ノード45: 32.0 m

**PIDパラメータ**: Kp=0.005, Ki=0.00005, Kd=0.003

**設定例**:
```json
{
  "control_mode": "pressure",
  "network": {"inp_file": "Net3.inp"},
  "control_loops": [
    {
      "loop_id": "loop_1",
      "target": {"node_id": "161", "target_pressure": 30.0},
      "actuator": {"link_id": "155", "initial_setting": 0.5},
      "pid_params": {"Kp": 0.005, "Ki": 0.00005, "Kd": 0.003}
    },
    {
      "loop_id": "loop_2",
      "target": {"node_id": "65", "target_pressure": 28.0},
      "actuator": {"link_id": "70", "initial_setting": 0.5},
      "pid_params": {"Kp": 0.005, "Ki": 0.00005, "Kd": 0.003}
    },
    {
      "loop_id": "loop_3",
      "target": {"node_id": "45", "target_pressure": 32.0},
      "actuator": {"link_id": "50", "initial_setting": 0.5},
      "pid_params": {"Kp": 0.005, "Ki": 0.00005, "Kd": 0.003}
    }
  ]
}
```

**引用論文**:
- EPANET 2.2 User Manual, Example 3 (Source Tracing)
- USEPA/WNTR Issue #210 - Net3 PDD Analysis

---

## 流量制御

### Net1

**ノード**: `2` (タンク供給後の主要ジャンクション)
**アクチュエータ**: `10` (FCV - Flow Control Valve)
**目標値**: 100.0 LPS (リットル/秒)
**PIDパラメータ**: Kp=0.02, Ki=0.0002, Kd=0.01

**設定例**:
```json
{
  "control_mode": "flow",
  "network": {"inp_file": "Net1.inp"},
  "control_loops": [{
    "loop_id": "loop_1",
    "target": {"node_id": "2", "target_flow": 100.0},
    "actuator": {"link_id": "10", "type": "FCV", "initial_setting": 0.5},
    "pid_params": {"Kp": 0.02, "Ki": 0.0002, "Kd": 0.01}
  }]
}
```

**引用論文**:
- Prescott, S.L., Ulanicki, B. (2008). "Improved Control of Pressure Reducing Valves in Water Distribution Networks." Journal of Hydraulic Engineering, ASCE.
- EPANET Manual - Flow Control Valves Section

---

### Net2

**ノード**: 
- `11` (主要供給地点)
- `19` (副供給地点)

**アクチュエータ**: 
- `25` (FCV - Zone 1)
- `30` (FCV - Zone 2)

**目標値**: 
- ノード11: 150.0 LPS
- ノード19: 120.0 LPS

**PIDパラメータ**: Kp=0.015, Ki=0.00015, Kd=0.008

**設定例**:
```json
{
  "control_mode": "flow",
  "network": {"inp_file": "Net2.inp"},
  "control_loops": [
    {
      "loop_id": "loop_1",
      "target": {"node_id": "11", "target_flow": 150.0},
      "actuator": {"link_id": "25", "type": "FCV", "initial_setting": 0.6},
      "pid_params": {"Kp": 0.015, "Ki": 0.00015, "Kd": 0.008}
    },
    {
      "loop_id": "loop_2",
      "target": {"node_id": "19", "target_flow": 120.0},
      "actuator": {"link_id": "30", "type": "FCV", "initial_setting": 0.5},
      "pid_params": {"Kp": 0.015, "Ki": 0.00015, "Kd": 0.008}
    }
  ]
}
```

**引用論文**:
- CCWI2017: "Comparison of Different Controllers for Equitable Water Supply in Water Networks"
- Campestrini, L. (2006). "Tuning of PID controllers decentralized based on method of critical point." UFRGS.

---

### Net3

**ノード**: 
- `161` (高需要地点)
- `65` (中需要地点)
- `45` (高地地点)

**アクチュエータ**: 
- `155` (FCV - Zone 1)
- `70` (FCV - Zone 2)
- `50` (FCV - Zone 3)

**目標値**: 
- ノード161: 200.0 LPS
- ノード65: 150.0 LPS
- ノード45: 100.0 LPS

**PIDパラメータ**: Kp=0.01, Ki=0.0001, Kd=0.005

**設定例**:
```json
{
  "control_mode": "flow",
  "network": {"inp_file": "Net3.inp"},
  "control_loops": [
    {
      "loop_id": "loop_1",
      "target": {"node_id": "161", "target_flow": 200.0},
      "actuator": {"link_id": "155", "type": "FCV", "initial_setting": 0.5},
      "pid_params": {"Kp": 0.01, "Ki": 0.0001, "Kd": 0.005}
    },
    {
      "loop_id": "loop_2",
      "target": {"node_id": "65", "target_flow": 150.0},
      "actuator": {"link_id": "70", "type": "FCV", "initial_setting": 0.5},
      "pid_params": {"Kp": 0.01, "Ki": 0.0001, "Kd": 0.005}
    },
    {
      "loop_id": "loop_3",
      "target": {"node_id": "45", "target_flow": 100.0},
      "actuator": {"link_id": "50", "type": "FCV", "initial_setting": 0.5},
      "pid_params": {"Kp": 0.01, "Ki": 0.0001, "Kd": 0.005}
    }
  ]
}
```

**引用論文**:
- Koşucu, M.M., Demirel, M.C. (2022). "Smart pressure management extension for EPANET." Journal of Hydroinformatics, 24(3), 642-658.
- CCWI2017: "Comparison of Different Controllers for Equitable Water Supply in Water Networks"

---

## 補足

### バルブタイプ

- **PRV** (Pressure Reducing Valve): 圧力制御用
- **FCV** (Flow Control Valve): 流量制御用
- **PCV** (Pressure Control Valve): 双方向圧力制御（MPC向き）

### 期待される性能（文献値）

| ネットワーク | 圧力制御 MAE | 流量制御 MAE |
|:---|:---:|:---:|
| Net1 | 1-3 m | 5-10 LPS |
| Net2 | 2-5 m | 10-20 LPS |
| Net3 | 3-8 m | 15-30 LPS |

### 注意事項

1. **ノードIDとリンクID**: 実際のネットワークファイル（.inp）で確認が必要
2. **目標値**: ネットワークの需要パターンに応じて調整
3. **PIDパラメータ**: 初期値として使用し、実験で調整
4. **流量制御**: 圧力制御ほど文献事例が多くないため、目標値は推定値

### 主要参考文献

1. **EPANET 2.2 User Manual** (EPA, 2020)
2. **Prescott & Ulanicki** (2008). Journal of Hydraulic Engineering
3. **CCWI2017**: Comparison of Different Controllers
4. **Koşucu & Demirel** (2022). Journal of Hydroinformatics
5. **EPyT Documentation** - EPANET Python Toolkit
