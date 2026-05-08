# CLAUDE.md

本文件为 Claude Code（claude.ai/code）在此代码仓库中工作时提供指导。

根目录的 `../CLAUDE.md` 涵盖两个子系统的总体说明，本文件补充 `fire_ground` 专项细节。

## 前置条件

本项目的传入参数为星上火点验证系统（https://github.com/hhhjuice/fire_satellite）的输出数据。在修改项目代码之前，请先了解火点验证系统项目的功能。

## 常用命令

在 `fire_ground/` 目录下运行：

```bash
# 启动服务
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001

# 运行全部测试
python -m pytest tests/ -v

# 运行单个测试文件
python -m pytest tests/test_heat_source_classifier.py -v

# 代码检查 / 格式化
ruff check app/ tests/
ruff format app/ tests/
```

Ruff 配置：`pyproject.toml`，Python 3.11，行长 120，规则 E/F/W/I（忽略 E501）。

## API 接口

| 方法     | 路径                                              | 说明                                                          |
| -------- | ------------------------------------------------- | ------------------------------------------------------------- |
| `POST` | `/api/enhance`                                  | 主流水线——接受 `EnhanceRequest`，返回 `EnhanceResponse` |
| `GET`  | `/api/health`                                   | 健康检查                                                      |
| `GET`  | `/api/history?limit=50`                         | 查询最近 DB 记录（范围 1–500）                               |
| `GET`  | `/api/history/nearby?lat=&lon=&radius_deg=0.05&limit=20` | 按低精度坐标网格查询 DB 记录                         |
| `GET`  | `/static/map.html`                              | Leaflet.js 前端地图                                           |

## 流水线架构

`enhance_batch` → 并发调用每个火点的 `enhance_single_point`：

1. **并行 I/O 阶段：** `get_historical_fires`（FIRMS，可选请求级 `firms_map_key`）+ `detect_industrial_heat`（OSM Overpass）+ `reverse_geocode`（Nominatim）——通过 `asyncio.gather(return_exceptions=True)` 并发执行，任一服务失败时降级，不影响整体流程
2. **融合阶段：** `compute_ground_confidence` → `determine_verdict`
3. **分类阶段（纯计算，无 I/O）：** `classify_heat_sources` 生成 `HeatSourceClassificationSchema`

单点处理异常时，批次回退为保留卫星判定结果，并附加原因 `[地面增强] 增强过程发生错误`。

## 置信度模型（`core/confidence.py`）

```text
logit(P_地面) = logit(P_卫星 / 100) + ln(LR_firms) + Δ_industrial
```

- `P_卫星` 是星上输出的 `final_confidence`，使用 0-100 百分制。
- `LR_firms` 来自 `FirmsMatchLevel` 对应配置：`GROUND_FIRMS_LR_EXACT_MATCH`、`GROUND_FIRMS_LR_NEARBY`、`GROUND_FIRMS_LR_REGIONAL`、`GROUND_FIRMS_LR_NO_HISTORY`。
- FIRMS 仅在 `status=success` 时参与置信度计算；未提供 key 或查询失败时为中性贡献，不把 `NO_HISTORY` 当负证据。
- `Δ_industrial` 来自 `IndustrialProximity` 对应配置：`GROUND_INDUSTRIAL_DELTA_WITHIN_500M`、`GROUND_INDUSTRIAL_DELTA_WITHIN_2KM`、`GROUND_INDUSTRIAL_DELTA_WITHIN_5KM`、`GROUND_INDUSTRIAL_DELTA_NONE`。
- 判决阈值：`≥ 75.0 → TRUE_FIRE`，`< 50.0 → FALSE_POSITIVE`，其余 `UNCERTAIN`。

## 热源分类器（`services/heat_source_classifier.py`）

纯计算，无网络 I/O。对 8 种类别使用加法规则模型打分，再经 softmax 归一化：

| 类别                                 | 关键触发条件                                          |
| ------------------------------------ | ----------------------------------------------------- |
| `vegetation_fire`（植被火灾）      | ESA 地物编码 10/20/30 + 高 FRP                        |
| `agricultural_burning`（农业焚烧） | 地物编码 40                                           |
| `industrial_heat`（工业热源）      | OSM 检测到工业设施                                    |
| `urban_heat_island`（城市热岛）    | 卫星 `urban_heat` 假阳性标志触发                    |
| `sun_glint`（太阳耀斑）            | 卫星 `sun_glint` 标志触发；夜间重罚                 |
| `water_reflection`（水体反射）     | 卫星 `water_body` 标志触发 + 地物编码 80            |
| `coastal_reflection`（海岸折射）   | 卫星 `coastal_reflection` 标志触发 + 地物编码 90/95 |
| `wetland_fire`（湿地火灾）         | 地物编码 90/95 且无海岸触发                           |

## 数据层

- **`data/osm.py`** — Overpass API 客户端，在边界框内查询工业/电力/制造设施
- **`data/cache.py`** — 基于 `aiosqlite` 的 SQLite 摘要持久化；只保存 15 天低精度 `lat_grid`/`lon_grid` 与判定摘要，不保存精确坐标、地址、完整 JSON 或 FIRMS key
- **`data/fire_ground.db`** — 首次运行时自动创建

## 配置项（`app/config.py`，前缀 `GROUND_`）

| 变量                             | 默认值                  | 说明                                                  |
| -------------------------------- | ----------------------- | ----------------------------------------------------- |
| `GROUND_DB_PATH`               | `data/fire_ground.db` | SQLite 数据库路径                                     |
| `GROUND_HISTORY_RETENTION_DAYS` | `15`                 | 历史摘要保留天数                                      |
| `GROUND_HISTORY_COORD_PRECISION_DEG` | `0.1`          | 历史坐标网格精度（度）                                |
| `GROUND_FIRMS_LR_EXACT_MATCH`  | `4.0`                 | FIRMS 1km 内命中似然比                                |
| `GROUND_FIRMS_LR_NEARBY`       | `2.5`                 | FIRMS 5km 内命中似然比                                |
| `GROUND_FIRMS_LR_REGIONAL`     | `1.5`                 | FIRMS 10km 内命中似然比                               |
| `GROUND_FIRMS_LR_NO_HISTORY`   | `0.5`                 | FIRMS 无记录似然比                                    |
| `GROUND_INDUSTRIAL_DELTA_WITHIN_500M` | `-2.5`        | 工业设施 500m 内 logit 修正                           |
| `GROUND_INDUSTRIAL_DELTA_WITHIN_2KM`  | `-1.5`        | 工业设施 2km 内 logit 修正                            |
| `GROUND_INDUSTRIAL_DELTA_WITHIN_5KM`  | `-0.8`        | 工业设施 5km 内 logit 修正                            |
| `GROUND_INDUSTRIAL_DELTA_NONE` | `0.3`                 | 附近无工业设施 logit 修正                             |
| `GROUND_HTTP_TIMEOUT`          | `10.0`                | HTTP 超时（秒），适用于 FIRMS、Overpass、Nominatim    |
| `GROUND_HTTP_USER_AGENT`       | `FireGroundEnhanceSystem/1.0` | 外部 API 请求 User-Agent                     |
| `GROUND_CORS_ORIGINS`          | `http://localhost:8001,http://127.0.0.1:8001` | 允许的浏览器来源，逗号分隔 |
| `GROUND_MAX_BATCH_RESULTS`     | `100`                 | 单次增强最大结果数                                    |
| `GROUND_CACHE_TTL_SECONDS`     | `3600`                | 内存缓存过期时间                                      |
| `GROUND_CACHE_MAX_SIZE`        | `1000`                | 内存缓存最大条目数                                    |

将 `.env.example` 复制为 `.env` 进行自定义配置。

## 数据模型（`app/api/schemas.py`）

`SatelliteResultInput` 完整镜像卫星系统输出——地面系统不重新计算任何卫星字段，包括新增的 `fire_area_m2`（火点估算面积，单位 m²）直接透传。`GroundEnhancedResult` 包装 `SatelliteResultInput` 并附加所有地面专属字段，包括 `heat_source_classification`。

所有原因说明均为中文，地面增强新增的原因统一以 `[地面增强]` 为前缀。
