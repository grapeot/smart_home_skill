# Smart Home Skill

英文版：[README.md](README.md)

Smart Home Skill 是一个本地运行、面向 AI agent 的智能家居控制层。它提供显式 HTTP API、实时 OpenAPI 文档和一个轻量 dashboard，让 agent 能基于真实部署配置操作家里的设备。

核心约定是：**OpenAPI 定义什么可以调用；private overlay 定义在这个家里应该怎么调用。**

## 支持的设备

| 集成 | 作用 |
|---|---|
| Hue | 通过 `phue` 读取和控制本地灯光 |
| Wemo | 通过 `pywemo` 和私有设备配置控制本地开关 |
| Rinnai | 通过 `aiorinnai` 读取热水器状态和触发循环 |
| Meross | 通过本地 HTTP `/config` 触发车库门；云端账号只用于发现本地设备和签名 key |
| Amcrest | 通过 Digest Auth 代理本地摄像头快照 |

## 设计原则

1. **OpenAPI 是 public source of truth。** Agent 执行动作前应读取运行中服务的 `GET /openapi.json`。
2. **Runtime API 保持显式。** 真实动作仍然是 `POST /api/garage/{door}/toggle` 这类专用 endpoint，而不是把意图藏在 generic `/execute` payload 里。
3. **Private overlay 承载家庭语义。** 设备别名、本地 IP、凭据、通知收件人、安全偏好和自然语言映射都不进 public repo。
4. **物理动作单独对待。** 车库门 toggle 只能用 POST，并可在触发成功后发送通知。
5. **Dashboard 是辅助界面。** UI 用于人类观察和调试；核心产品是 agent-readable 的本地控制层。

## Public/Private 组织方式

Public repo 保存可复用代码、schema、文档、测试和安全示例。

本地部署增加私有状态：

| 本地文件或 overlay | 用途 | Git 状态 |
|---|---|---|
| `.env` | 凭据、端口、Resend 通知配置 | ignored |
| `config/wemo_config.yaml` | 真实 Wemo 设备名和本地 IP | ignored |
| `config/cameras.yaml` | 真实摄像头名和本地 IP | ignored |
| Workspace private skill overlay | 自然语言别名、默认设备、安全规则、家庭策略 | public repo 外部 |

Private overlay 不应该复制完整 API。它只补 OpenAPI 不知道的本地语义。

## Agent 调用流程

Agent 调设备 API 前应该：

1. 确认服务健康：`GET /health`。
2. 获取实时 schema：`GET /openapi.json`。
3. 只用 private overlay 做名称映射、安全策略和默认值判断。
4. 确认目标 endpoint 和 HTTP method 存在于 OpenAPI。
5. 调用显式 endpoint。
6. 检查 response，尤其是敏感动作里的 `status`、`error` 和 `notification` 字段。

示例：

```bash
curl -sS http://localhost:7999/openapi.json >/tmp/smart_home_openapi.json
curl -sS -X POST http://localhost:7999/api/garage/2/toggle
```

## 快速开始

```bash
cd smart_home
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
cp config/wemo_config.example.yaml config/wemo_config.yaml
cp config/cameras.example.yaml config/cameras.yaml
```

修改这些私有文件以匹配你的家，不要提交它们。

```bash
./scripts/build-frontend.sh
./scripts/start-backend.sh
```

macOS 生产运行建议使用能继承 Local Network 权限的前台启动链路。本 workspace 使用 Process Launcher 调用 `./start_server.sh`。不要用 PM2 管理这个服务。

## API 发现

| URL | 用途 |
|---|---|
| `/openapi.json` | 给 agent 使用的机器可读 API contract |
| `/docs` | Swagger UI |
| `/redoc` | ReDoc UI |
| `/health` | 健康检查 |

README 中的 endpoint 表只做导览；实际 contract 以 `/openapi.json` 为准。

## 车库控制器遥测

默认情况下车库 toggle 响应不返回 Meross 控制器的原始字段（`backend`、`previous_state`、`reported_state`、`final_state`、`executed`）。这些是控制器的指令方向状态，不是物理传感器读数。多数家庭没有安装磁传感器，透传这些字段会让调用方误以为遥测就是门的真实位置。确认门状态请用 visual check。

在 `.env` 中设置 `MEROSS_GARAGE_EXPOSE_CONTROLLER_TELEMETRY=true` 可在响应中包含这些原始字段，适用于已安装物理传感器或需要调试/集成的场景。`GarageToggleResponse` 的 OpenAPI schema 描述了哪些字段是遥测专用。

## 测试

```bash
source .venv/bin/activate
python -m pytest test/ -q --ignore=test/test_integration_real.py

cd frontend
npm test -- --run
npm run build
```

完整测试策略见 [docs/test.md](docs/test.md)。
