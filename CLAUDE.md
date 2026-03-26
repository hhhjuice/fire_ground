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
| `GET`  | `/api/history/nearby?lat=&lon=&radius_deg=0.05` | 按坐标范围查询 DB 记录                                        |
| `GET`  | `/static/map.html`                              | Leaflet.js 前端地图                                           |

## 流水线架构

`enhance_batch` → 并发调用每个火点的 `enhance_single_point`：

1. **并行 I/O 阶段：** `get_historical_fires`（FIRMS）+ `detect_industrial_heat`（OSM Overpass）+ `reverse_geocode`（Nominatim）——通过 `asyncio.gather(return_exceptions=True)` 并发执行，任一服务失败时降级为 `None`，不影响整体流程
2. **融合阶段：** `compute_ground_confidence` → `determine_verdict`
3. **分类阶段（纯计算，无 I/O）：** `classify_heat_sources` 生成 `HeatSourceClassificationSchema`

单点处理异常时，批次回退为保留卫星判定结果，并附加原因 `[地面增强] 增强过程发生错误`。

## 置信度模型（`core/confidence.py`）

```text
logit(P_地面) = logit(P_卫星) + β_hist × hist_score − industrial_penalty
```

- `β_hist = 0.3`（可通过 `GROUND_BETA_HIST` 配置）
- `industrial_penalty` 来自 `IndustrialFalsePositiveResult.flag.penalty`（默认 `0.8`，可通过 `GROUND_FP_PENALTY_INDUSTRIAL` 配置）
- 判决阈值**硬编码**：≥ 0.75 → `TRUE_FIRE`，< 0.35 → `FALSE_POSITIVE`（与卫星系统不同，不可通过配置修改）

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
- **`data/cache.py`** — 基于 `aiosqlite` 的 SQLite 持久化；核心函数：`save_enhancement_result`、`get_recent_enhancements`、`get_nearby_enhancements`
- **`data/fire_ground.db`** — 首次运行时自动创建

## 配置项（`app/config.py`，前缀 `GROUND_`）

| 变量                             | 默认值                  | 说明                                                  |
| -------------------------------- | ----------------------- | ----------------------------------------------------- |
| `GROUND_FIRMS_MAP_KEY`         | `DEMO_KEY`            | DEMO_KEY 有速率限制，可在 NASA FIRMS 免费申请正式密钥 |
| `GROUND_DB_PATH`               | `data/fire_ground.db` | SQLite 数据库路径                                     |
| `GROUND_BETA_HIST`             | `0.3`                 | 历史数据权重                                          |
| `GROUND_FP_PENALTY_INDUSTRIAL` | `0.8`                 | 工业热源 logit 惩罚值                                 |
| `GROUND_HTTP_TIMEOUT`          | `10.0`                | HTTP 超时（秒），适用于 FIRMS、Overpass、Nominatim    |
| `GROUND_CACHE_TTL_SECONDS`     | `3600`                | 内存缓存过期时间                                      |
| `GROUND_CACHE_MAX_SIZE`        | `1000`                | 内存缓存最大条目数                                    |

将 `.env.example` 复制为 `.env` 进行自定义配置。

## 数据模型（`app/api/schemas.py`）

`SatelliteResultInput` 完整镜像卫星系统输出——地面系统不重新计算任何卫星字段，包括新增的 `fire_area_m2`（火点估算面积，单位 m²）直接透传。`GroundEnhancedResult` 包装 `SatelliteResultInput` 并附加所有地面专属字段，包括 `heat_source_classification`。

所有原因说明均为中文，地面增强新增的原因统一以 `[地面增强]` 为前缀。
