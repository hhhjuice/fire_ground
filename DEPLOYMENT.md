# 地面火点增强验证系统 — 部署与使用文档

## 目录

1. [系统概述](#1-系统概述)
2. [环境要求](#2-环境要求)
3. [安装部署](#3-安装部署)
4. [NASA FIRMS API Key 申请](#4-nasa-firms-api-key-申请)
5. [配置说明](#5-配置说明)
6. [启动服务](#6-启动服务)
7. [API 使用](#7-api-使用)
8. [前端地图使用](#8-前端地图使用)
9. [置信度算法说明](#9-置信度算法说明)
10. [故障排查](#10-故障排查)
11. [运维说明](#11-运维说明)

---

## 1. 系统概述

地面火点增强验证系统（`fire_ground`）是部署于地面站的火点增强分析服务。它接收星上主判系统（`fire_satellite`）通过星地链路下传的验证结果，叠加仅在地面可用的网络数据源，输出最终增强判定结果。

系统在星上结果基础上叠加以下三类分析：

- **历史火点验证**：查询 NASA FIRMS（VIIRS SNPP、VIIRS NOAA-20、MODIS NRT 三个源）过去 5 天内指定范围的历史火灾记录，有历史记录则提升置信度
- **工业设施假阳性排查**：通过 OSM Overpass API 检查火点坐标附近的工业设施（钢铁厂、炼油厂等高温工业热源），命中则降低置信度
- **反向地理编码**：通过 Nominatim 将坐标转换为可读地址，附加于结果说明中

系统**不重复**星上已完成的工作：地物分析、环境因素计算、坐标修正等均直接使用星上结果，地面系统只在星上置信度基础上做增量修正。

### 与星上系统的关系

```
卫星传感器 → fire_satellite（主判）→ JSON 结果
                                         |
                                    星地链路下传
                                         |
                                         v
                              fire_ground（地面增强）
                                         |
                               +---------+---------+
                               |         |         |
                           FIRMS       OSM    Nominatim
                         历史火点    工业设施    地理编码
```

地面系统提供 Leaflet.js 交互式前端地图，可在浏览器中直接粘贴星上 JSON 或手动输入坐标进行增强验证。结果持久化至本地 SQLite 数据库，支持历史查询。

---

## 2. 环境要求

### 硬件最低要求

| 资源 | 最低                   | 推荐       |
| ---- | ---------------------- | ---------- |
| CPU  | 1 核                   | 2 核+      |
| 内存 | 256 MB                 | 1 GB+      |
| 存储 | 500 MB（含 SQLite）    | 5 GB+      |
| 网络 | **必须有互联网** | 低延迟宽带 |

> **注意**：地面系统依赖互联网。NASA FIRMS、OSM Overpass、Nominatim 均为外部网络服务。若网络不通，这三项分析将降级返回默认值，但系统仍可正常运行，只是增强效果缺失。

### 软件要求

- Python **3.11+**
- 操作系统：Linux / macOS / Windows（推荐 Linux）
- 无需 GDAL（地面系统不读取 GeoTIFF）

---

## 3. 安装部署

### 3.1 方式一：pip 安装（推荐生产环境）

```bash
# 进入项目目录
cd fire_ground

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate        # Linux / macOS
# .venv\Scripts\activate         # Windows

# 安装依赖
pip install -r requirements.txt
```

### 3.2 方式二：Conda 安装（推荐开发环境）

```bash
# 创建或激活 Conda 环境
conda create -n fire python=3.11 -y
conda activate fire

# 安装依赖
pip install -r requirements.txt
```

### 3.3 验证安装

```bash
python -c "import fastapi, httpx, aiosqlite, pydantic; print('依赖安装成功')"
```

### 3.4 创建数据目录

SQLite 数据库将在启动时自动创建于 `data/` 目录，首次启动前需确认目录存在：

```bash
mkdir -p data
```

---

## 4. NASA FIRMS API Key 申请

历史火点查询依赖 NASA FIRMS API Key。默认配置使用 `DEMO_KEY`，**DEMO_KEY 有严格速率限制**，生产环境务必申请正式 Key。

### 4.1 申请步骤

1. 访问 https://firms.modaps.eosdis.nasa.gov/api/map_key/
2. 点击 **"Get a MAP KEY"**
3. 使用 NASA Earthdata 账号登录（或免费注册：https://urs.earthdata.nasa.gov/）
4. 填写申请表，Key 将立即生成并显示，同时发送至注册邮箱

### 4.2 Key 权限说明

| Key 类型 | 每日请求上限  | 说明                   |
| -------- | ------------- | ---------------------- |
| DEMO_KEY | 约 30 次/小时 | 仅供测试，严禁生产使用 |
| 正式 Key | 无明确限制    | 免费，注册即得         |

### 4.3 验证 Key 有效性

```bash
# 替换 YOUR_KEY 后执行，返回 CSV 数据说明 Key 有效
curl "https://firms.modaps.eosdis.nasa.gov/api/area/csv/YOUR_KEY/VIIRS_SNPP_NRT/116,28,117,29/1"
```

---

## 5. 配置说明

### 5.1 创建配置文件

```bash
cp .env.example .env
```

### 5.2 配置项详解

编辑 `.env` 文件：

```ini
# ── NASA FIRMS 配置 ────────────────────────────────────────
# NASA FIRMS Map Key（务必替换为正式申请的 Key）
GROUND_FIRMS_MAP_KEY=your_key_here

# FIRMS API 地址（通常不需修改）
GROUND_FIRMS_BASE_URL=https://firms.modaps.eosdis.nasa.gov/api/area/csv

# ── OSM Overpass 配置 ──────────────────────────────────────
# OSM Overpass API 地址（可替换为自建实例以提升稳定性）
GROUND_OVERPASS_URL=https://overpass-api.de/api/interpreter

# ── Nominatim 地理编码配置 ─────────────────────────────────
# Nominatim 地址（可替换为自建实例以遵守 OSM 使用条款）
GROUND_NOMINATIM_URL=https://nominatim.openstreetmap.org/reverse

# ── 置信度权重参数 ─────────────────────────────────────────
# 历史火点数据在 logit 空间的贡献权重
# 较大值 → 历史数据影响更大；较小值 → 历史数据影响较弱
GROUND_BETA_HIST=0.3

# 工业设施假阳性惩罚值（在 logit 空间直接减去）
# 较大值 → 工业设施附近的火点更容易被判为假阳性
GROUND_FP_PENALTY_INDUSTRIAL=0.8

# ── 缓存配置 ──────────────────────────────────────────────
# FIRMS 查询结果缓存有效期（秒）
GROUND_CACHE_TTL_SECONDS=3600

# 缓存最大条目数（LRU 策略，超出后淘汰最旧条目）
GROUND_CACHE_MAX_SIZE=1000

# ── 数据库配置 ────────────────────────────────────────────
# SQLite 数据库路径（相对于项目根目录，或绝对路径）
GROUND_DB_PATH=data/fire_ground.db

# ── HTTP 客户端配置 ───────────────────────────────────────
# 外部 API 请求超时时间（秒）
GROUND_HTTP_TIMEOUT=10.0
```

### 5.3 环境变量优先级

系统按以下顺序读取配置（后者覆盖前者）：

1. 代码中的默认值
2. `.env` 文件
3. 系统环境变量（`export GROUND_FIRMS_MAP_KEY=your_key`）

### 5.4 生产环境注意

`main.py` 中 CORS 设置为 `allow_origins=["*"]`，适用于开发和内网部署。若需对公网开放，建议修改为具体域名：

```python
# app/main.py 中修改
allow_origins=["https://your-domain.com"]
```

---

## 6. 启动服务

### 6.1 开发模式（自动热重载）

```bash
cd fire_ground
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

### 6.2 生产模式（多 Worker）

```bash
# 根据 CPU 核数调整 workers
uvicorn app.main:app --host 0.0.0.0 --port 8001 --workers 4
```

### 6.3 后台运行（systemd）

创建服务文件 `/etc/systemd/system/fire-ground.service`：

```ini
[Unit]
Description=地面火点增强验证系统
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/fire_ground
EnvironmentFile=/opt/fire_ground/.env
ExecStart=/opt/fire_ground/.venv/bin/uvicorn app.main:app \
    --host 0.0.0.0 --port 8001 --workers 2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable fire-ground
sudo systemctl start fire-ground
sudo systemctl status fire-ground
```

### 6.4 验证启动成功

```bash
curl http://localhost:8001/api/health
# 期望输出：{"status":"ok","version":"1.0.0","services":{"pipeline":true,"database":true}}
```

启动日志应包含：

```
INFO     app.main: Starting Ground Fire Enhancement System...
INFO     app.data.cache: Database initialized at data/fire_ground.db
INFO     app.main: System ready.
INFO     uvicorn: Application startup complete.
```

浏览器访问 `http://localhost:8001` 应自动跳转至 Leaflet 前端地图页面。

---

## 7. API 使用

### 7.1 POST /api/enhance — 地面增强验证

这是系统的核心端点。接收星上系统 `/api/validate` 的完整输出 JSON，对每个火点叠加地面增强分析后返回增强结果。

**完整请求示例：**

```bash
curl -X POST http://localhost:8001/api/enhance \
  -H "Content-Type: application/json" \
  -d '{
    "results": [
      {
        "input_point": {
          "latitude": 28.5,
          "longitude": 116.3,
          "satellite": "VIIRS",
          "brightness": 345.2,
          "frp": 25.8,
          "confidence": 80,
          "acquisition_time": "2026-03-11T06:00:00Z"
        },
        "verdict": "TRUE_FIRE",
        "final_confidence": 0.84,
        "reasons": ["地物类型为草地，属于高火灾风险区域", "高亮温 (345.2K > 340K)，为活跃火点增加置信度"],
        "summary": "星上主判结果为真实火点，最终置信度 84.0%。",
        "coordinate_correction": {
          "original_lat": 28.5,
          "original_lon": 116.3,
          "corrected_lat": 28.5012,
          "corrected_lon": 116.3018,
          "offset_m": 185.3,
          "correction_applied": true,
          "reason": "修正至最近可燃区域(草地)"
        },
        "landcover": {
          "class_code": 30,
          "class_name": "草地",
          "likelihood_ratio": 3.0,
          "description": "ESA WorldCover 2021: 草地 (编码30)"
        },
        "false_positive": {
          "flags": [],
          "total_penalty": 0.0,
          "is_likely_false_positive": false
        },
        "environmental": {
          "is_daytime": true,
          "solar_zenith_angle": 42.3,
          "fire_season_factor": 1.2,
          "env_score": 0.15,
          "detail": "白天观测，夏季北半球"
        },
        "confidence_breakdown": null,
        "processing_time_ms": 38.5
      }
    ]
  }'
```

**最简请求（仅提供星上核心字段）：**

```bash
curl -X POST http://localhost:8001/api/enhance \
  -H "Content-Type: application/json" \
  -d '{
    "results": [
      {
        "input_point": {"latitude": 28.5, "longitude": 116.3},
        "verdict": "TRUE_FIRE",
        "final_confidence": 0.84,
        "reasons": [],
        "summary": "星上主判结果为真实火点",
        "coordinate_correction": null,
        "landcover": null,
        "false_positive": {"flags": [], "total_penalty": 0.0, "is_likely_false_positive": false},
        "environmental": null,
        "confidence_breakdown": null,
        "processing_time_ms": 0
      }
    ]
  }'
```

**将星上输出直接管道到地面系统：**

```bash
# 第一步：调用星上系统
SAT_RESULT=$(curl -s -X POST http://localhost:8000/api/validate \
  -H "Content-Type: application/json" \
  -d '{"points": [{"latitude":30.03039, "longitude":119.74884, "acquisition_time": "2026-03-11T14:30:00Z"}]}')

# 第二步：提取 results 数组，构造地面系统输入
GROUND_INPUT=$(echo $SAT_RESULT | python3 -c \
  "import json,sys; d=json.load(sys.stdin); print(json.dumps({'results': d['results']}))")

# 第三步：调用地面系统
curl -X POST http://localhost:8001/api/enhance \
  -H "Content-Type: application/json" \
  -d "$GROUND_INPUT"
```

**请求字段说明（`results` 数组中每个对象）：**

| 字段                      | 类型         | 必填 | 说明                                                         |
| ------------------------- | ------------ | ---- | ------------------------------------------------------------ |
| `input_point.latitude`  | float        | ✅   | 纬度                                                         |
| `input_point.longitude` | float        | ✅   | 经度                                                         |
| `input_point.*`         | 各类型       | 否   | 其他传感器参数（原样透传至响应）                             |
| `verdict`               | string       | ✅   | 星上判定：`TRUE_FIRE` / `UNCERTAIN` / `FALSE_POSITIVE` |
| `final_confidence`      | float        | ✅   | 星上最终置信度（0~1），作为地面增强的起点                    |
| `reasons`               | array        | ✅   | 星上判定原因列表（地面增强后追加地面原因）                   |
| `summary`               | string       | ✅   | 星上综合摘要                                                 |
| `coordinate_correction` | object\|null | 否   | 星上坐标修正信息，若修正则地面查询修正后坐标                 |
| `landcover`             | object\|null | 否   | 星上地物分析结果（透传）                                     |
| `false_positive`        | object       | ✅   | 星上假阳性检测结果                                           |
| `environmental`         | object\|null | 否   | 星上环境因素分析（透传）                                     |
| `confidence_breakdown`  | object\|null | 否   | 星上置信度分解（透传）                                       |
| `processing_time_ms`    | float        | ✅   | 星上处理耗时（ms）                                           |

**响应示例：**

```json
{
  "results": [
    {
      "satellite_result": { "...原始星上结果（完整透传）..." },
      "ground_verdict": "TRUE_FIRE",
      "ground_confidence": 0.88,
      "ground_reasons": [
        "地物类型为草地，属于高火灾风险区域",
        "[地面增强] 过去5天内半径5km范围发现 3 个历史火点，最近距离 800m"
      ],
      "ground_summary": "地面增强判定为真实火点，最终置信度 88.0%。",
      "historical": {
        "nearby_fire_count": 3,
        "nearest_distance_m": 800.0,
        "days_searched": 30,
        "score": 0.52,
        "detail": "过去30天内半径5km范围发现3个历史火点，最近距离800m"
      },
      "industrial_fp": {
        "flag": {
          "detector": "industrial_facility",
          "triggered": false,
          "penalty": 0.0,
          "detail": null
        }
      },
      "ground_confidence_breakdown": {
        "satellite_confidence": 0.84,
        "historical_contribution": 0.156,
        "industrial_penalty": 0.0,
        "final_confidence": 0.88
      },
      "geocoding_address": "中国江西省南昌市青山湖区",
      "processing_time_ms": 1430.5
    }
  ],
  "total_points": 1,
  "true_fire_count": 1,
  "false_positive_count": 0,
  "uncertain_count": 0,
  "total_processing_time_ms": 1430.5
}
```

**响应字段说明：**

| 字段                              | 说明                                                                    |
| --------------------------------- | ----------------------------------------------------------------------- |
| `satellite_result`              | 完整的星上原始结果（原样透传）                                          |
| `ground_verdict`                | 地面增强最终判定                                                        |
| `ground_confidence`             | 地面增强最终置信度（0~1）                                               |
| `ground_reasons`                | 合并后的原因列表：星上原因 + 地面增强原因（以 `[地面增强]` 前缀区分） |
| `ground_summary`                | 地面综合摘要                                                            |
| `historical.nearby_fire_count`  | 范围内历史火点数量                                                      |
| `historical.nearest_distance_m` | 最近历史火点距离（米），无记录时为 null                                 |
| `historical.score`              | 历史火点得分（-1 ~ 1），正值提升置信度，负值降低                        |
| `industrial_fp.flag.triggered`  | 是否命中工业设施检测器                                                  |
| `industrial_fp.flag.penalty`    | 工业设施惩罚值（0 或配置的 `GROUND_FP_PENALTY_INDUSTRIAL`）           |
| `ground_confidence_breakdown`   | 地面置信度分解：星上置信度 + 历史贡献 - 工业惩罚                        |
| `geocoding_address`             | 反向地理编码地址（网络异常时为 null）                                   |
| `processing_time_ms`            | 地面增强处理耗时（ms，通常 500~3000ms，取决于网络）                     |

---

### 7.2 GET /api/health — 健康检查

```bash
curl http://localhost:8001/api/health
```

```json
{
  "status": "ok",
  "version": "1.0.0",
  "services": {
    "pipeline": true,
    "database": true
  }
}
```

---

### 7.3 GET /api/history — 查询历史记录

返回数据库中最近 N 条增强结果的摘要。

```bash
# 最近 10 条
curl "http://localhost:8001/api/history?limit=10"

# 最多 500 条
curl "http://localhost:8001/api/history?limit=500"
```

**参数：**

| 参数      | 类型 | 默认值 | 范围    | 说明         |
| --------- | ---- | ------ | ------- | ------------ |
| `limit` | int  | 50     | 1 ~ 500 | 返回记录数量 |

**返回：** 数组，每项包含 `id`、`latitude`、`longitude`、`satellite_verdict`、`satellite_confidence`、`ground_verdict`、`ground_confidence`、`summary`、`result_json`（完整 JSON 字符串）、`created_at`。

---

### 7.4 GET /api/history/nearby — 查询附近历史记录

查询指定坐标附近的历史增强结果，用于判断某区域是否曾有火点记录。

```bash
# 查询 (28.5°N, 116.3°E) 附近 0.05° 范围内的历史记录
curl "http://localhost:8001/api/history/nearby?lat=28.5&lon=116.3&radius_deg=0.05"

# 扩大搜索范围至 0.1°（约 11km）
curl "http://localhost:8001/api/history/nearby?lat=28.5&lon=116.3&radius_deg=0.1"
```

**参数：**

| 参数           | 类型  | 默认值 | 范围       | 说明                            |
| -------------- | ----- | ------ | ---------- | ------------------------------- |
| `lat`        | float | —     | -90 ~ 90   | 中心点纬度（必填）              |
| `lon`        | float | —     | -180 ~ 180 | 中心点经度（必填）              |
| `radius_deg` | float | 0.05   | 0 ~ 1.0    | 搜索半径（度），0.05° ≈ 5.5km |

**返回：** 最多 20 条记录，格式同 `/api/history`，按时间倒序排列。

---

### 7.5 Swagger 交互式文档

浏览器访问 `http://localhost:8001/docs`，可在页面上直接构造请求并查看完整响应模型。

---

## 8. 前端地图使用

浏览器访问 `http://localhost:8001`（自动跳转）或 `http://localhost:8001/static/map.html`，进入 Leaflet.js 交互式前端。

### 8.1 界面说明

前端采用绿色主题，与星上系统区分。主要区域：

- **左侧控制面板**：输入区域，支持两种输入模式切换
- **右侧地图**：Leaflet 地图，增强完成后在地图上显示火点标记，点击标记查看详情

### 8.2 JSON 输入模式

适用于已有星上系统输出的场景。

1. 在控制面板顶部选择 **"JSON 输入"** 标签
2. 将星上系统 `/api/validate` 的完整响应 JSON 粘贴至文本框
3. 点击 **"提交增强"**
4. 系统自动提取 `results` 数组发送至 `/api/enhance`
5. 增强结果显示在右侧地图，点击标记查看详细信息

### 8.3 手动输入模式

适用于快速测试或手动录入坐标的场景。

1. 在控制面板顶部选择 **"手动输入"** 标签
2. 填写以下字段：

| 字段       | 说明                                   | 示例          |
| ---------- | -------------------------------------- | ------------- |
| 纬度       | 火点纬度（必填）                       | `28.5`      |
| 经度       | 火点经度（必填）                       | `116.3`     |
| 星上判定   | TRUE_FIRE / UNCERTAIN / FALSE_POSITIVE | `TRUE_FIRE` |
| 星上置信度 | 0~1 之间的小数                         | `0.84`      |

3. 点击 **"提交增强"**，系统以默认值构造星上结果后发送增强请求

### 8.4 地图标记颜色说明

| 颜色 | 判定结果       | 说明                   |
| ---- | -------------- | ---------------------- |
| 红色 | TRUE_FIRE      | 地面增强确认为真实火点 |
| 黄色 | UNCERTAIN      | 不确定，建议人工复核   |
| 蓝色 | FALSE_POSITIVE | 地面增强判定为假阳性   |

---

## 9. 置信度算法说明

### 核心公式

```
logit(P_ground) = logit(P_satellite) + beta_hist * hist_score - industrial_penalty
```

各项含义：

| 项                         | 公式                      | 说明                                                |
| -------------------------- | ------------------------- | --------------------------------------------------- |
| `logit(P_satellite)`     | `ln(P_sat / (1-P_sat))` | 星上最终置信度转换到 logit 空间，作为地面增强的起点 |
| `beta_hist * hist_score` | beta=0.3，score∈[-1, 1]  | 历史火点贡献，正值提升，负值降低                    |
| `industrial_penalty`     | 0 或 0.8                  | 工业设施惩罚，命中则在 logit 空间减去 0.8           |

最终通过 sigmoid 映射回 0–1：

```
P_ground = sigmoid(logit_score) = 1 / (1 + e^(-logit_score))
```

### 历史火点得分计算

历史得分 `hist_score` 由 FIRMS 查询结果计算：

```
hist_score = 0.7 * dist_factor + 0.3 * count_factor

dist_factor  = max(0, 1 - nearest_distance / radius)   # 越近得分越高
count_factor = min(1, log(1+count) / log(1+20))         # 对数归一化，>20 个时饱和
```

- 无历史火点：`hist_score = -0.3`（轻微降低置信度）
- 半径内有大量近距离火点：`hist_score` 接近 1.0（显著提升置信度）

FIRMS 并行查询 3 个数据源（VIIRS SNPP NRT、VIIRS NOAA-20 NRT、MODIS NRT）并合并去重，查询天数上限为 **5 天**（受 FIRMS API 限制，与请求中 `days_back` 参数无关）。

### 判定阈值

地面系统使用与星上系统相同的判定阈值：

```
P_ground >= 0.75  →  TRUE_FIRE      （真实火点）
P_ground <  0.35  →  FALSE_POSITIVE  （假阳性）
0.35 <= P_ground < 0.75  →  UNCERTAIN  （待确认）
```

### 典型场景示例

| 场景                 | 星上置信度 | 历史得分 | 工业惩罚 | 地面置信度 | 判定      |
| -------------------- | ---------- | -------- | -------- | ---------- | --------- |
| 有历史记录的真实火点 | 0.84       | +0.52    | 0        | 0.88       | TRUE_FIRE |
| 无历史记录的孤立火点 | 0.72       | -0.09    | 0        | 0.70       | UNCERTAIN |
| 工业区高温热源       | 0.55       | 0        | 0.8      | 0.37       | UNCERTAIN |
| 工业区 + 有历史记录  | 0.70       | +0.3     | 0.8      | 0.63       | UNCERTAIN |

---

## 10. 故障排查

### 问题：历史火点查询结果始终为 0，或返回"历史火点查询失败"

**可能原因一：FIRMS API Key 无效**

```bash
# 检查日志是否有以下报错
# WARNING app.services.historical: FIRMS query failed (source=VIIRS_SNPP_NRT days=5): ...

# 手动测试 Key（替换 YOUR_KEY）
curl "https://firms.modaps.eosdis.nasa.gov/api/area/csv/YOUR_KEY/VIIRS_SNPP_NRT/116,28,117,29/1"
# 正常返回 CSV 数据；返回 HTML 错误页说明 Key 无效
```

**解决：** 检查 `.env` 中的 `GROUND_FIRMS_MAP_KEY`，确认已填入正式申请的 Key，而非 `DEMO_KEY`。

---

**可能原因二：网络不通或 FIRMS 服务不可用**

```bash
# 测试网络连通性
curl -I https://firms.modaps.eosdis.nasa.gov/
```

**解决：** 检查服务器网络出口规则，确认可访问 `firms.modaps.eosdis.nasa.gov`（443 端口）。

---

**可能原因三：该区域确实无历史火点**

系统正常行为，历史得分将为 -0.3（轻微降低置信度）。

---

### 问题：工业设施检测总是返回 `triggered: false`

**可能原因：** OSM Overpass API 超时或返回空结果。

```bash
# 手动测试 Overpass API
curl -X POST "https://overpass-api.de/api/interpreter" \
  --data '[out:json][timeout:10];node["landuse"="industrial"](around:500,28.5,116.3);out;'
```

**解决：**

- 若返回超时，增大 `GROUND_HTTP_TIMEOUT`（如设为 20.0）
- 若该区域确实无工业设施，属正常结果
- 若频繁超时，可自建 Overpass 实例（https://overpass-api.de/full_installation.html）

---

### 问题：geocoding_address 始终为 null

**原因：** Nominatim 公共服务有使用限制（1 次/秒），高频请求可能被限流。

```bash
# 测试 Nominatim 连通性
curl "https://nominatim.openstreetmap.org/reverse?lat=28.5&lon=116.3&format=json"
# 正常返回 JSON；返回 HTTP 429 说明被限流
```

**解决：**

- 降低请求频率（Nominatim 官方要求生产环境自建实例）
- 参考 https://nominatim.org/release-docs/develop/api/Overview/#usage-policy 了解使用条款
- 自建 Nominatim 后修改 `GROUND_NOMINATIM_URL` 指向内部实例

---

### 问题：服务启动报 `aiosqlite` 相关错误

**原因：** `aiosqlite` 未安装，或数据目录不存在。

```bash
# 确认安装
pip show aiosqlite

# 确认数据目录存在
ls -la data/
```

**解决：**

```bash
pip install aiosqlite
mkdir -p data
```

---

### 问题：增强响应时间很长（> 10 秒）

**原因：** 三个外部 API（FIRMS、OSM、Nominatim）并行请求，若某个响应慢会影响总耗时。

FIRMS 每个数据源有 6 秒超时限制（`FIRMS_SOURCE_TIMEOUT = 6.0`），三个源并行查询，总计最长等待约 7 秒。

**解决：**

- 检查网络质量，或选用延迟更低的 API 节点
- 可将 `GROUND_HTTP_TIMEOUT` 降低至 6.0，提前放弃慢速请求（部分结果可能缺失）

---

### 问题：服务启动报 `Address already in use`

**原因：** 端口 8001 被占用。

```bash
# 查找占用进程
lsof -i :8001

# 换端口启动
uvicorn app.main:app --host 0.0.0.0 --port 8002
```

---

## 11. 运维说明

### 日志管理

服务日志输出到 stdout，格式为：

```
2026-03-11 10:00:01,234 INFO  app.main: Starting Ground Fire Enhancement System...
2026-03-11 10:00:01,256 INFO  app.data.cache: Database initialized at data/fire_ground.db
2026-03-11 10:00:01,260 INFO  app.main: System ready.
2026-03-11 10:00:05,120 WARNING app.services.historical: FIRMS query failed (source=MODIS_NRT days=5): timeout
```

生产环境建议重定向到文件并配置日志轮转：

```bash
uvicorn app.main:app ... 2>&1 | tee -a /var/log/fire-ground.log
```

### SQLite 数据库

数据库文件默认位于 `data/fire_ground.db`，路径可通过 `GROUND_DB_PATH` 配置。

**查询历史增强结果：**

```bash
sqlite3 data/fire_ground.db \
  "SELECT created_at, latitude, longitude, satellite_verdict, ground_verdict, ground_confidence \
   FROM enhancement_results ORDER BY created_at DESC LIMIT 20;"
```

**数据库大小估算：** 每条记录约 2–5 KB（含完整 result_json），每天 1000 次请求约产生 2–5 MB 数据。建议定期归档：

```bash
# 删除 30 天前的记录并压缩数据库
sqlite3 data/fire_ground.db "DELETE FROM enhancement_results WHERE created_at < datetime('now', '-30 days');"
sqlite3 data/fire_ground.db "VACUUM;"
```

### FIRMS 缓存说明

FIRMS 查询结果缓存于内存（LRU + TTL），TTL 默认 3600 秒（1 小时）。同一区域、同一天数内的重复查询直接命中缓存，不发起网络请求。缓存在服务重启后清空。

缓存最大条目数由 `GROUND_CACHE_MAX_SIZE` 控制，超出后按 LRU 策略淘汰最旧条目。

### 运行测试

```bash
cd fire_ground
python -m pytest tests/ -v
# 期望：32 passed
```

### 性能基准

| 条件              | 典型响应时间 | 说明                     |
| ----------------- | ------------ | ------------------------ |
| FIRMS 缓存命中    | 200–500 ms  | OSM + Nominatim 仍需请求 |
| 全部外部 API 正常 | 800–2500 ms | 三路并行，取最慢者       |
| 某个 API 超时     | 约 7 秒      | FIRMS 单源 6 秒超时      |
| 所有外部 API 不通 | < 100 ms     | 全部降级，返回默认值     |

> 地面系统响应时间主要由网络质量决定，与星上系统（本地 GeoTIFF 磁盘读取）特性不同。
