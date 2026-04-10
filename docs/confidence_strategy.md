# 置信度修正策略

## 概述

火点置信度经由**两阶段修正流水线**产生最终判决结果：

1. **Stage 1 — 星上验证**（本项目，离线）：基于地物类型、环境因素和假阳性检测
2. **Stage 2 — 地面验证**（地面系统）：基于 FIRMS 历史火点数据和工业设施检测

两个阶段共享同一 **Bayesian Logit 框架**，修正量在 logit 空间叠加，保持数学一致性。

---

## 置信度流向

```
检测接口输出  confidence ∈ [50, 75]
         │
         │ ÷100 → P₀ ∈ [0.50, 0.75]  →  logit(P₀) ∈ [0, 1.10]
         ▼
┌──────────────────────────────────────────────────────────┐
│  Stage 1：星上验证（本项目）                                │
│                                                          │
│  logit(Pₛ) = logit(P₀) + ln(LR_lc)                      │
│              + β·env_score − Σ fp_penalty                │
│                                                          │
│  初步判决阈值：≥75 → TRUE_FIRE，<50 → FALSE_POSITIVE       │
└───────────────────────┬──────────────────────────────────┘
                        │ sigmoid × 100 → sat_confidence ∈ [0, 100]
                        ▼
┌──────────────────────────────────────────────────────────┐
│  Stage 2：地面验证（地面系统）                              │
│                                                          │
│  logit(P_final) = logit(Pₛ/100)                          │
│                   + ln(LR_firms)                         │
│                   + Δ_industrial                         │
│                                                          │
│  最终判决阈值：≥75 → TRUE_FIRE，<50 → FALSE_POSITIVE       │
└───────────────────────┬──────────────────────────────────┘
                        ▼
              final_confidence ∈ [0, 100]
    真实火点 [75, 100] | 不确定 [50, 75) | 假阳性 < 50
```

---

## Stage 1：星上验证

### 公式

```
logit(Pₛ) = logit(P₀) + ln(LR_lc) + β_env × env_score − Σ fp_penalty
Pₛ = sigmoid(logit(Pₛ)) × 100
```

### 输入

| 参数 | 来源 | 说明 |
|------|------|------|
| P₀ | 检测接口 `confidence/100` | 传感器原始置信度，[0.50, 0.75] |
| LR_lc | 本地 GeoTIFF 查询 | ESA WorldCover 地物似然比 |
| env_score | 纯数学计算 | 太阳角度 + 季节，∈ [-0.5, 0.5] |
| fp_penalty | 4 种检测器 | 水体/城市/耀光/海岸 |

### 地物似然比（LR_lc）

| 代码 | 类别 | LR | Δlogit |
|------|------|----|--------|
| 30 | 草地 | 4.0 | +1.39 |
| 20 | 灌木地 | 3.5 | +1.25 |
| 10 | 林地 | 3.0 | +1.10 |
| 40 | 农田 | 2.0 | +0.69 |
| 90 | 草本湿地 | 1.5 | +0.41 |
| 95 | 红树林 | 1.2 | +0.18 |
| 100 | 苔藓/地衣 | 1.0 | 0 |
| 50 | 建成区 | 0.2 | −1.61 |
| 60 | 裸地/稀疏植被 | 0.05 | −3.00 |
| 70 | 冰雪 | 0.01 | −4.61 |
| 80 | 水体 | 0.01 | −4.61 |

### 假阳性惩罚（fp_penalty）

| 检测器 | 触发条件 | Δlogit |
|--------|---------|--------|
| 水体 | landcover == 80 | −3.0 |
| 城市热岛 | landcover == 50 | −1.5 |
| 海岸反射 | landcover ∈ {90, 95} | −1.2 |
| 太阳耀光 | 天顶角 ∈ [60°, 85°] | −1.0 |

### 初步判决阈值（`config.py`）

| 阈值 | 默认值 | 初步判决 |
|------|--------|---------|
| `SAT_THRESHOLD_TRUE_FIRE` | 75.0 | ≥75 → 疑似真实火点 |
| `SAT_THRESHOLD_FALSE_POSITIVE` | 50.0 | <50 → 疑似假阳性 |

> 星上与地面阶段使用相同阈值（75/50），保持两阶段判决标准一致。

---

## Stage 2：地面验证

### 公式

```
logit(P_final) = logit(Pₛ/100) + ln(LR_firms) + Δ_industrial
P_final = sigmoid(logit(P_final)) × 100
```

### 2.1 FIRMS 近期火点修正（LR_firms）

使用 NASA FIRMS NRT 接口，查询近 **5 天**、**10km 范围**内的卫星热点记录，按距离分级：

| 场景 | LR | Δlogit | 环境变量 |
|------|----|--------|---------|
| 1km内有近期火点 | 4.0 | +1.39 | `GROUND_FIRMS_LR_EXACT_MATCH` |
| 5km内有近期火点 | 2.5 | +0.92 | `GROUND_FIRMS_LR_NEARBY` |
| 10km内有近期火点 | 1.5 | +0.41 | `GROUND_FIRMS_LR_REGIONAL` |
| 10km内无记录 | 0.5 | −0.69 | `GROUND_FIRMS_LR_NO_HISTORY` |

> **数据源限制**：FIRMS NRT 仅提供近 5 天数据，不支持多年历史或季节匹配。

### 2.2 工业设施检测修正（Δ_industrial）

工业热源（电厂、钢铁厂、化工厂、水泥厂等）是热红外传感器最常见的假阳性来源：

| 场景 | Δlogit | 环境变量 |
|------|--------|---------|
| 工业设施 < 500m | −2.5 | `GROUND_INDUSTRIAL_DELTA_WITHIN_500M` |
| 工业设施 500m–2km | −1.5 | `GROUND_INDUSTRIAL_DELTA_WITHIN_2KM` |
| 工业设施 2–5km | −0.8 | `GROUND_INDUSTRIAL_DELTA_WITHIN_5KM` |
| 5km 内无工业设施 | +0.3 | `GROUND_INDUSTRIAL_DELTA_NONE` |

**特殊情况 — 油气火炬（Gas Flare）**：油气井燃烧放空属于真实燃烧源，`is_gas_flare=True` 时**跳过**工业设施惩罚，不修改置信度。

### 最终判决阈值

| `final_confidence` | 最终判决 | 含义 |
|-------------------|---------|------|
| ≥ 75 | `TRUE_FIRE` | 星上+地面双重确认 |
| [50, 75) | `UNCERTAIN` | 证据不足以确认或排除 |
| < 50 | `FALSE_POSITIVE` | 双重否定证据充分 |

---

## 典型场景验证

### 场景 A — 强真实火点（草地 + FIRMS 近期记录）

```
输入: 70  → logit = 0.847
星上: 草地 LR=4.0 (+1.386) + 良好环境 (+0.25) = +1.636
  → logit = 2.483  → Pₛ = 92.3%
地面: FIRMS 同位置命中 (+1.386) + 无工业设施 (+0.3) = +1.686
  → logit = 4.169  → P_final ≈ 98.5%  ✓ TRUE_FIRE
```

### 场景 B — 不确定（农田 + 无历史记录）

```
输入: 62  → logit = 0.490
星上: 农田 LR=2.0 (+0.693) + 中性环境 (0) = +0.693
  → logit = 1.183  → Pₛ = 76.5%
地面: 10km 内无 FIRMS (−0.693) + 无工业 (+0.3) = −0.393
  → logit = 0.790  → P_final ≈ 68.8%  ✓ UNCERTAIN
```

### 场景 C — 工业设施假阳性（建成区 + 电厂 500m）

```
输入: 70  → logit = 0.847
星上: 建成区 LR=0.2 (−1.609) + 太阳耀光 (−1.0) = −2.609
  → logit = −1.762  → Pₛ = 14.6%
地面: 无 FIRMS 历史 (−1.20) + 电厂 <500m (−2.5) = −3.70
  → logit = −5.462  → P_final ≈ 0.4%  ✓ FALSE_POSITIVE
```

### 场景 D — 偏远草地无历史记录（地物强支持）

```
输入: 60  → logit = 0.405
星上: 灌木地 LR=3.5 (+1.253) + 好季节 (+0.2) = +1.453
  → logit = 1.858  → Pₛ = 86.5%
地面: 10km 无 FIRMS (−0.693) + 无工业 (+0.3) = −0.393
  → logit = 1.465  → P_final ≈ 81.2%  ✓ TRUE_FIRE
（偏远地区无历史不代表无火，地物强支持时仍判真实火点）
```

---

## 接口协议

星上系统输出 `SatelliteValidationResult`，地面系统以此为输入计算 `GroundValidationResult`：

```
SatelliteValidationResult          GroundValidationResult
─────────────────────────    →    ──────────────────────────────
final_confidence (0-100)           verdict (TRUE_FIRE/…)
verdict (初步, 75/50)              final_confidence (0-100)
landcover / environmental          firms: FirmsResult
false_positive                     industrial: IndustrialResult
confidence_breakdown               confidence_breakdown
```

相关 Schema 定义见 `app/api/schemas.py`，地面阶段计算逻辑见 `app/core/confidence.py`。
