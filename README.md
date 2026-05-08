# 地面火点增强验证系统 (fire_ground)

地面端火点增强验证系统。接收星上主判系统的输出结果，叠加网络依赖的增强分析（NASA FIRMS 历史火点、OSM 工业设施检测、Nominatim 反向地理编码），输出最终地面增强判定。FIRMS MAP key 由前端或请求体按次提供；未提供时跳过历史火点查询，不把“无历史记录”作为负证据。

**不重复星上已完成的工作** — 地物分析、环境因素、坐标修正等均直接使用星上结果。

## 特点

- **增量增强** — 仅在星上置信度基础上叠加地面独有的分析维度
- **历史火点验证** — NASA FIRMS 近期火灾记录查询
- **工业设施检测** — OSM Overpass 工业热源假阳性排查
- **反向地理编码** — Nominatim 获取可读地址
- **热源类型分类** — 8 类热源（植被火灾、农业焚烧、工业热源等）概率排名，直接展示星上 `fire_area_m2`
- **Leaflet.js 交互式前端** — 地图可视化，支持 JSON 输入和手动输入
- **SQLite 持久化** — 仅保存 15 天低精度网格摘要，可查询历史记录且不保存精确坐标/地址/完整 JSON

## 系统架构

```text
星上系统输出 (JSON)
        |
        v
   FastAPI POST /api/enhance
        |
        v
   增强 Pipeline 编排器
        |
        +-- 并行执行 ----------------+
        |   +-- 历史火点 (NASA FIRMS)
        |   +-- 工业设施检测 (OSM)
        |   +-- 反向地理编码 (Nominatim)
        |
        +-- 融合
        |   +-- 地面置信度 = f(星上置信度, 历史, 工业)
        |   +-- 地面判定
        |   +-- 地面原因生成 ("[地面增强]" 前缀)
        |
        +-- 分类 (纯计算，无 I/O)
        |   +-- 热源类型分类 (8 类, softmax)
        |
        +-- 输出
            +-- SQLite 持久化
            +-- 返回增强结果
```

## 置信度算法

```text
logit(P_ground) = logit(P_satellite / 100) + ln(LR_firms) + delta_industrial
```

| 参数 | 说明 | 默认值 |
| --- | --- | --- |
| P_satellite | 星上最终置信度，0-100 百分制 (直接使用，不重算) | - |
| LR_firms | FIRMS 匹配等级对应似然比；仅在 FIRMS 查询成功时参与计算 | 4.0 / 2.5 / 1.5 / 0.5 |
| delta_industrial | 工业设施距离等级对应 logit 修正 | -2.5 / -1.5 / -0.8 / +0.3 |

**判定阈值：** 同星上系统 (`>= 75.0 TRUE_FIRE`, `< 50.0 FALSE_POSITIVE`, 其余 `UNCERTAIN`)

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# FIRMS MAP key 在前端 FIRE_FIRMS_MAP_KEY 输入框或 API 请求体 firms_map_key 中按次填写

# 启动服务
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001

# 浏览器访问前端
open http://localhost:8001
```

启动后可访问：

- `http://localhost:8001` — Leaflet 地图前端
- `http://localhost:8001/docs` — Swagger API 文档

## API

### POST /api/enhance — 地面增强验证

接收星上系统的输出 JSON，返回地面增强结果。

**请求体：**

```json
{
  "firms_map_key": "YOUR_FIRMS_MAP_KEY",
  "results": [
    {
      "input_point": {
        "latitude": 28.5,
        "longitude": 116.3,
        "confidence": 80,
        "acquisition_time": "2026-03-08T06:00:00Z"
      },
      "verdict": "TRUE_FIRE",
      "final_confidence": 82.0,
      "fire_area_m2": 2500.0,
      "reasons": ["地物类型为草地，属于高火灾风险区域"],
      "summary": "星上主判结果为真实火点，最终置信度 82.0%。",
      "coordinate_correction": null,
      "landcover": { "class_code": 30, "class_name": "草地", "likelihood_ratio": 3.0, "description": "草地火灾风险较高" },
      "false_positive": { "flags": [], "total_penalty": 0.0, "is_likely_false_positive": false },
      "environmental": { "is_daytime": true, "solar_zenith_angle": 42.0, "fire_season_factor": 1.3, "env_score": 0.15, "detail": "处于火险季节" },
      "confidence_breakdown": {
        "initial_confidence": 80.0,
        "landcover_contribution": 1.099,
        "environmental_contribution": 0.075,
        "false_positive_penalty": 0.0,
        "final_confidence": 82.0
      },
      "processing_time_ms": 45.2
    }
  ]
}
```

**响应体：**

```json
{
  "results": [
    {
      "satellite_result": { "...星上原始结果..." },
      "ground_verdict": "TRUE_FIRE",
      "ground_confidence": 86.0,
      "ground_reasons": [
        "地物类型为草地，属于高火灾风险区域",
        "[地面增强] 该区域近期有 5 次火灾记录，最近距离 1200m"
      ],
      "ground_summary": "地面增强判定为真实火点，最终置信度 86.0%。",
      "firms": { "status": "success", "match_level": "NEARBY", "nearest_fire_km": 1.2, "nearest_fire_date": "2026-03-06T00:00:00", "detail": "5km内发现近期火点，距离1.20km" },
      "industrial": { "proximity": "NONE", "nearest_facility_m": null, "facility_type": null, "is_gas_flare": false, "detail": "10km内无工业设施" },
      "ground_confidence_breakdown": {
        "satellite_confidence": 82.0,
        "firms_contribution": 0.9163,
        "industrial_contribution": 0.3,
        "final_confidence": 86.0
      },
      "geocoding_address": "中国江西省南昌市",
      "heat_source_classification": {
        "top_type": "vegetation_fire",
        "top_label_zh": "植被火灾",
        "top_probability": 0.7231,
        "ranked_sources": [
          { "type": "vegetation_fire", "label_zh": "植被火灾", "probability": 0.7231, "raw_score": 4.3 },
          { "type": "agricultural_burning", "label_zh": "农业焚烧", "probability": 0.1542, "raw_score": 1.8 }
        ]
      },
      "processing_time_ms": 1820.3
    }
  ],
  "total_points": 1,
  "true_fire_count": 1,
  "false_positive_count": 0,
  "uncertain_count": 0,
  "total_processing_time_ms": 1820.3
}
```

### GET /api/health — 健康检查

```json
{ "status": "ok", "version": "1.0.0", "services": { "pipeline": true, "database": true } }
```

### GET /api/history?limit=50 — 历史增强记录

返回最近 N 条增强结果摘要。历史仅保留 15 天，坐标以 `lat_grid`/`lon_grid` 低精度网格保存，不返回精确经纬度、反向地理编码地址或完整增强 JSON。

### GET /api/history/nearby?lat=28.5&lon=116.3&radius_deg=0.05&limit=20 — 附近历史记录

返回指定坐标附近的低精度历史增强结果，可通过 `limit` 控制返回数量。

## 项目结构

```text
fire_ground/
  app/
    main.py                       # FastAPI 入口 (含前端、DB 初始化、CORS)
    config.py                     # 配置 (GROUND_ 前缀环境变量)
    api/
      routes.py                   # 4 个 API 端点
      schemas.py                  # Pydantic 数据模型
    core/
      confidence.py               # 地面置信度引擎 (在星上结果上叠加)
      pipeline.py                 # 增强 Pipeline (历史 + 工业 + 编码并行)
    data/
      cache.py                    # SQLite 摘要持久化 + TTL/LRU 工具
      osm.py                      # OSM Overpass API 客户端
    services/
      false_positive.py           # 工业设施假阳性检测 (仅此一种)
      geocoding.py                # Nominatim 反向地理编码
      historical.py               # NASA FIRMS 历史火点查询
      heat_source_classifier.py   # 热源类型分类 (纯计算，8 类 softmax)
    utils/
      geo.py                      # 地理计算 (haversine, bbox 等)
      reason_generator.py         # 中文原因生成 ("[地面增强]" 前缀)
  static/
    map.html                      # Leaflet.js 交互式前端
  data/                           # SQLite 数据库目录
  tests/                          # 65 个单元测试
  requirements.txt
  pyproject.toml
  .env.example
```

## 配置项

所有配置通过环境变量设置，前缀 `GROUND_`：

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| GROUND_FIRMS_BASE_URL | FIRMS API 地址 | <https://firms.modaps.eosdis.nasa.gov/api/area/csv> |
| GROUND_OVERPASS_URL | OSM Overpass 地址 | <https://overpass-api.de/api/interpreter> |
| GROUND_NOMINATIM_URL | Nominatim 地址 | <https://nominatim.openstreetmap.org/reverse> |
| GROUND_FIRMS_LR_EXACT_MATCH | FIRMS 1km 内命中似然比 | 4.0 |
| GROUND_FIRMS_LR_NEARBY | FIRMS 5km 内命中似然比 | 2.5 |
| GROUND_FIRMS_LR_REGIONAL | FIRMS 10km 内命中似然比 | 1.5 |
| GROUND_FIRMS_LR_NO_HISTORY | FIRMS 无记录似然比 | 0.5 |
| GROUND_INDUSTRIAL_DELTA_WITHIN_500M | 工业设施 500m 内 logit 修正 | -2.5 |
| GROUND_INDUSTRIAL_DELTA_WITHIN_2KM | 工业设施 2km 内 logit 修正 | -1.5 |
| GROUND_INDUSTRIAL_DELTA_WITHIN_5KM | 工业设施 5km 内 logit 修正 | -0.8 |
| GROUND_INDUSTRIAL_DELTA_NONE | 附近无工业设施 logit 修正 | 0.3 |
| GROUND_CACHE_TTL_SECONDS | 缓存 TTL (秒) | 3600 |
| GROUND_CACHE_MAX_SIZE | 缓存最大条目 | 1000 |
| GROUND_DB_PATH | SQLite 路径 | data/fire_ground.db |
| GROUND_HISTORY_RETENTION_DAYS | 历史摘要保留天数 | 15 |
| GROUND_HISTORY_COORD_PRECISION_DEG | 历史坐标网格精度 (度) | 0.1 |
| GROUND_HTTP_TIMEOUT | HTTP 超时 (秒) | 10.0 |
| GROUND_HTTP_USER_AGENT | 外部 API 请求 User-Agent | FireGroundEnhanceSystem/1.0 |
| GROUND_CORS_ORIGINS | 允许的浏览器来源，逗号分隔 | http://localhost:8001,http://127.0.0.1:8001 |
| GROUND_MAX_BATCH_RESULTS | 单次增强最大结果数 | 100 |

## 测试

```bash
python -m pytest tests/ -v
```

65 个测试覆盖：地面置信度引擎、FIRMS key 降级语义、历史摘要脱敏、API 降级路径、地理计算、原因生成、数据模型验证、缓存工具、热源类型分类。

## 前端使用

前端支持两种输入模式：

1. **JSON 模式** — 直接粘贴星上系统的 `/api/validate` 输出 JSON
2. **手动模式** — 填写经纬度等字段，系统自动构造默认星上结果

`FIRE_FIRMS_MAP_KEY` 输入框为可选；留空时跳过 FIRMS 历史火点查询，地面置信度不会应用 `NO_HISTORY` 负贡献。

前端主题色为绿色，与星上系统区分。

## 与星上系统对接

```text
火点传感器 -> 星上系统 (fire_satellite:8000) -> JSON 输出
                                                   |
                                                   v (星地链路)
                                                   |
              地面系统 (fire_ground:8001) <- JSON 输入
                        |
                        v
                  增强结果 + 地图可视化
```

地面系统不重复星上已完成的工作，只在星上结果基础上叠加网络依赖的增强分析（历史火点、工业设施、地理编码）。
