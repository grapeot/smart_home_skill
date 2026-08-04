# Smart Home Ring Nightly Sensor Check 调研

本轮调研回答一个具体问题：现有晚上 9 点 camera visual check 已经能检查三处门/栅栏，Ring 是否适合加入同一个 nightly safety check，用传感器状态补充视觉判断。

结论：不要直接在 `visual_check_service` 里塞 Ring。更稳的路径是把 Ring 做成独立 telemetry source，再由 nightly wrapper 汇总 camera evidence 和 sensor telemetry。Ring 官方开发者平台现在偏 camera/video/event appstore 场景，公开材料没有给个人本地脚本一个稳定的 Ring Alarm contact sensor consumer API。若已经有 Ring Alarm Base Station 和 Ring contact sensors，MVP 应直接用 `ring-client-api` 做一次性 pull；`ring-mqtt` 只适合后续需要常驻事件流或 Home Assistant/MQTT discovery 时再引入。若还没绑定 Ring monitoring，本地 Z-Wave/HA/Z-Wave JS 更可靠。

## 当前系统落点

现有 9 点任务在 `adhoc_jobs/background_job_manager/config/launcher.yaml:103-114`：`nightly_garage_visual_check` 每天 `21:00 America/Los_Angeles` 执行 `.venv/bin/python config/visual_check_private/nightly_garage_check.py`，工作目录是 `adhoc_jobs/smart_home`。

现有检查脚本在 `adhoc_jobs/smart_home/config/visual_check_private/nightly_garage_check.py`。它先调用 `GET /api/visual-checks` 找到 `group=nightly` 的 checks，再逐个 `POST /api/visual-checks/{check_id}/run`，每项最多重试 3 次。`needs_notification()` 现在只看三类信号：visual check `status != ok`、`overall.any_door_open/any_gate_open == true`、assertion failed。

现有 nightly checks 在 `adhoc_jobs/smart_home/config/vision_checks.yaml:14-50`：

| check | camera_id | assertion |
|---|---|---|
| `garage` | `garage` | `$.overall.any_door_open == false` |
| `heat_pump_side_door` | `heat_pump_side_door` | `$.overall.any_gate_open == false` |
| `downstairs_side_door` | `downstairs_side_door` | `$.overall.any_gate_open == false` |

`smart_home` 现在没有 Ring 模块。`api/status.py:17` 只认 `hue,wemo,rinnai,garage`，`main.py:175-183` 只 include 这些 router 加 camera/schedule/visual_check。有限范围内搜 `Ring|ring|Alarm|alarm|security`，没有发现已存在 Ring/Alarm integration；唯一 `security` 命中是 `hashlib.md5(..., usedforsecurity=False)`。

## Ring 方案判断

Ring 官方开发者页说开发者可以访问 Ring APIs / Ring MCP Server，能力包括 live video、motion events、doorbell presses、device status、event history；示例流程是授权 app、接收 motion webhook、拉 WebRTC 视频流、添加 CV/AI 模型。来源：[Ring Developer](https://developer.amazon.com/ring)。这更像面向 Ring Appstore/certified app 的 camera/video 平台，公开材料没有明确说普通个人脚本可以读取 Ring Alarm Contact Sensor / Motion Detector 的实时 open/closed state。

Home Assistant 官方 Ring integration 也印证了这个边界。它支持 Ring.com doorbell、stick up cam、chime、intercom，并明确说所有通信走 Ring cloud、每 60 秒 polling；公开文档没有把 Ring Alarm contact sensors 作为支持对象。来源：[Home Assistant Ring integration](https://www.home-assistant.io/integrations/ring/)。

社区方案里，`ring-client-api` 明确覆盖 Ring Doorbells、Cameras、Alarm System、Smart Lighting，以及接入 Ring Alarm System 的第三方设备。它能拿到 location、alarm mode、devices，以及 `faulted`、`tamperStatus` 等字段；但它是非官方 API，依赖 refresh token，npm README 明确提醒 Ring refresh tokens 使用后会很快过期，需要正确处理 token lifecycle。来源：[ring-client-api npm](https://www.npmjs.com/package/ring-client-api)。

`ring-mqtt` 把 Ring alarm、camera、smart lighting 暴露为 MQTT topics，并支持 Home Assistant MQTT discovery；项目 wiki 说明它依赖 `ring-client-api`。实际讨论和日志里能看到 sensor state、battery、commStatus、lastUpdate、linkQuality、tamperStatus 这类字段。来源：[ring-mqtt wiki](https://github.com/tsightler/ring-mqtt/wiki) 和 [ring-mqtt discussion #815](https://github.com/tsightler/ring-mqtt/discussions/815)。不过这也说明 `ring-mqtt` 并不是绕开 Ring cloud 或绕开 `ring-client-api` 的更底层数据源。对 nightly pull 这个目标，MQTT broker、常驻 bridge、topic discovery 都是额外运维面。

2026-07-06 补充复核：`ring-mqtt` 最新 GitHub `package.json` 依赖 `@tsightler/ring-client-api`，release v5.9.3 也写明 dependency update 到 `ring-client-api 14.3.1-beta.0 (custom)`，并修了 push receiver、sporadic authentication 等问题。也就是说，`ring-mqtt` 的稳定性优势主要来自它作为长期运行服务在 token/state/push/MQTT 映射上做了封装，不是来自另一个更官方、更本地的 Ring 数据通道。

Ring Alarm Contact Sensor 2nd Gen 的手册说明两个关键事实：第一，在 Ring app 里启用 Contact Sensor 功能需要 Ring Alarm Base Station；第二，它本身是 Z-Wave 设备，可以在其他 Z-Wave certified network 中运行。来源：[Ring Alarm Contact Sensor Gen 2 Z-Wave Technical Manual](https://d1kusojqr3t85q.cloudfront.net/jrz4hnnvdyct/3AXPQshkruQCZPoSNuSzGp/b5c4b8cbf916293475e20fd1efa1a81d/Ring_Alarm_Contact_Sensor_Gen_2_Zwave_NA.pdf)。这意味着如果要保留 Ring app / Ring monitoring，就走 Base Station + ring-mqtt；如果只是要本地传感器，Z-Wave 直连更可靠。

## 推荐实现路径

第一步先不要碰现有 visual check engine。先做一个最小 Node pull spike：`adhoc_jobs/smart_home/scripts/ring_client_status.mjs`，用 `ring-client-api` + refresh token 直接输出 JSON。登录说明和验收标准在 `adhoc_jobs/smart_home/docs/ring_client_status_spike.md`。

第二步如果 spike 成立，再新增只读 Ring telemetry adapter：`services/ring_service.py` + `api/ring.py` + `models/schemas.py`，暴露 `GET /api/ring/status`。如果要纳入聚合状态，再把 `ring` 加进 `api/status.py:17` 的 `ALL_DEVICES` 和 `get_all_status()` 分支。

第三步改 nightly wrapper，而不是改 `VisualCheckService`。在 `config/visual_check_private/nightly_garage_check.py` 的 `main()` 里，先跑现有 `run_visual_check()`，再调用 `/api/ring/status`，最后由一个新的 `build_incident_decision(camera_result, ring_status)` 决定是否通知。这样 camera artifacts、Ring telemetry、最终 decision 三层分开。

第四步通知改成一封聚合邮件。现在 `format_body()` 只展示 visual check；加入 Ring 后应该展示：最终结论、camera check 摘要、Ring sensor 摘要、冲突状态、stale/error、artifact path。不要让 camera 和 Ring 各发一封，否则 Pushover 噪声会变高。

建议数据形态：

```json
{
  "source": "ring_mqtt",
  "observed_at": "2026-07-06T21:00:03-07:00",
  "stale": false,
  "error": null,
  "sensors": [
    {
      "id": "...",
      "name": "Front Door",
      "kind": "contact",
      "state": "closed",
      "battery_level": 90,
      "tamper_status": "ok",
      "comm_status": "ok",
      "last_update": "..."
    }
  ]
}
```

最终 decision 不要压成一个裸 boolean。更有用的是 `reason_codes`：`camera_open`、`sensor_open`、`camera_failed`、`sensor_stale`、`evidence_conflict`、`all_clear`。冲突状态尤其重要：camera 看到 open 但 Ring closed，或者 camera failed 但 Ring open，这两种都应该通知，但邮件里要说清楚证据来源冲突。

## 风险和约束

Ring cloud 路径不是本地物理真相。Contact sensor 也会有离线、低电量、tamper、安装偏移、同步延迟、云端 API 失败。现有 smart_home overlay 已经把 Meross garage telemetry 标成非权威，Ring 也应保持同一语义：它是 telemetry，不是最终真相。

token 生命周期是主要运维风险。`ring-client-api` 和 `ring-mqtt` 都依赖 refresh token/2FA 认证；token、location id、sensor id 都是私有 presence data。不要把它们放进 `background_job_manager/config/launcher.yaml` 或 periodic job env，因为 launcher 的配置和运行状态可能进入日志或 SQLite。更合理的是让 `smart_home` 服务自己从 `.env` 或 1Password reference 读取，nightly 脚本只打本地 HTTP。

Home Assistant 官方 Ring integration 不适合这个目标。它适合 Ring camera/doorbell/chime/intercom，而不是 Ring Alarm contact sensor 状态源。若已经跑 Home Assistant，可以让 `ring-mqtt` 把 entities 暴露给 HA，再由 smart_home 读 HA API/MQTT state；不要误以为官方 HA Ring integration 就能解决 contact sensors。

只接 Ring camera/doorbell 不够。要读取门窗 contact sensors，有两条路：Ring Alarm Base Station 管着这些 sensors，然后用 `ring-mqtt`/`ring-client-api` 读；或者把 Z-Wave sensors 直接配到本地 Z-Wave network。Camera/doorbell 本身不会充当 Ring Alarm contact sensor hub。

## 建议下一步

先做一个不控制任何设备的 spike：运行 `npm run ring:auth` 拿 refresh token，再运行 `npm run ring:status` 拉一次状态。验证标准是能看到 Ring Alarm Base Station、目标 contact sensors、`faulted/tamper/battery/lastUpdate` 等字段，并且手动开关一扇门后状态会变化。

如果 spike 成立，再连续跑 24-48 小时的定时 pull，观察 token 是否稳定、状态是否 stale、9 点附近延迟是否可接受。这个阶段仍然不用 MQTT。

最后改 `nightly_garage_check.py` 做证据融合和聚合通知。实现前需要定一张私有 mapping 表：Ring sensor name/id 对应哪个物理门，以及和现有三个 visual check 的对应关系。
