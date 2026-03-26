# 地面火点增强验证系统 (fire_ground)

地面端火点增强验证系统。接收星上主判系统的输出结果，叠加网络依赖的增强分析（NASA FIRMS 历史火点、OSM 工业设施检测、Nominatim 反向地理编码），输出最终地面增强判定。

**不重复星上已完成的工作** — 地物分析、环境因素、坐标修正等均直接使用星上结果。

## 特点

- **增量增强** — 仅在星上置信度基础上叠加地面独有的分析维度
- **历史火点验证** — NASA FIRMS 近期火灾记录查询
- **工业设施检测** — OSM Overpass 工业热源假阳性排查
- **反向地理编码** — Nominatim 获取可读地址
- **热源类型分类** — 8 类热源（植被火灾、农业焚烧、工业热源等）概率排名，直接展示星上 `fire_area_m2`
- **Leaflet.js 交互式前端** — 地图可视化，支持 JSON 输入和手动输入
- **SQLite 持久化** — 增强结果入库，可查询历史记录
- **LRU 缓存** — FIRMS 查询结果缓存，减少重复请求

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
logit(P_ground) = logit(P_satellite) + beta_hist * hist_score - industrial_penalty
```

| 参数 | 说明 | 默认值 |
| --- | --- | --- |
| P_satellite | 星上最终置信度 (直接使用，不重算) | - |
| beta_hist | 历史数据权重 | 0.3 |
| hist_score | 历史火点得分 ([-1, 1]) | - |
| industrial_penalty | 工业设施惩罚 | 0.8 |

**判定阈值：** 同星上系统 (>= 0.75 TRUE_FIRE, < 0.35 FALSE_POSITIVE, 其余 UNCERTAIN)

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入 NASA FIRMS API Key

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
  "results": [
    {
      "input_point": {
        "latitude": 28.5,
        "longitude": 116.3,
        "satellite": "VIIRS",
        "brightness": 340,
        "frp": 15.2,
        "confidence": 80,
        "acquisition_time": "2026-03-08T06:00:00Z"
      },
      "verdict": "TRUE_FIRE",
      "final_confidence": 0.82,
      "reasons": ["地物类型为草地，属于高火灾风险区域"],
      "summary": "星上主判结果为真实火点，最终置信度 82.0%。",
      "coordinate_correction": null,
      "landcover": { "class_code": 30, "class_name": "草地", "likelihood_ratio": 3.0 },
      "false_positive": { "flags": [], "total_penalty": 0.0 },
      "environmental": { "is_daytime": true, "env_score": 0.15 },
      "confidence_breakdown": null,
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
      "ground_confidence": 0.86,
      "ground_reasons": [
        "地物类型为草地，属于高火灾风险区域",
        "[地面增强] 该区域近期有 5 次火灾记录，最近距离 1200m"
      ],
      "ground_summary": "地面增强判定为真实火点，最终置信度 86.0%。",
      "historical": { "nearby_fire_count": 5, "nearest_distance_m": 1200, "score": 0.6 },
      "industrial_fp": { "flag": { "triggered": false } },
      "ground_confidence_breakdown": {
        "satellite_confidence": 0.82,
        "historical_contribution": 0.18,
        "industrial_penalty": 0.0,
        "final_confidence": 0.86
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

返回最近 N 条增强结果。

### GET /api/history/nearby?lat=28.5&lon=116.3&radius_deg=0.05 — 附近历史记录

返回指定坐标附近的历史增强结果。

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
      cache.py                    # LRU 缓存 + SQLite 持久化
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
  tests/                          # 48 个单元测试
  requirements.txt
  pyproject.toml
  .env.example
```

## 配置项

所有配置通过环境变量设置，前缀 `GROUND_`：

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| GROUND_FIRMS_MAP_KEY | NASA FIRMS API Key | DEMO_KEY |
| GROUND_FIRMS_BASE_URL | FIRMS API 地址 | <https://firms.modaps.eosdis.nasa.gov/api/area/csv> |
| GROUND_OVERPASS_URL | OSM Overpass 地址 | <https://overpass-api.de/api/interpreter> |
| GROUND_NOMINATIM_URL | Nominatim 地址 | <https://nominatim.openstreetmap.org/reverse> |
| GROUND_BETA_HIST | 历史数据权重 | 0.3 |
| GROUND_FP_PENALTY_INDUSTRIAL | 工业设施惩罚值 | 0.8 |
| GROUND_CACHE_TTL_SECONDS | 缓存 TTL (秒) | 3600 |
| GROUND_CACHE_MAX_SIZE | 缓存最大条目 | 1000 |
| GROUND_DB_PATH | SQLite 路径 | data/fire_ground.db |
| GROUND_HTTP_TIMEOUT | HTTP 超时 (秒) | 10.0 |

## 测试

```bash
python -m pytest tests/ -v
```

48 个测试覆盖：地面置信度引擎、地理计算、原因生成、数据模型验证、LRU 缓存、热源类型分类。

## 前端使用

前端支持两种输入模式：

1. **JSON 模式** — 直接粘贴星上系统的 `/api/validate` 输出 JSON
2. **手动模式** — 填写经纬度等字段，系统自动构造默认星上结果

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
