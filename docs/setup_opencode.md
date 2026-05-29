# OpenCode Server 本地安装配置

OpenCode Server 是 ASP 项目的默认本地 Agent 执行环境，用于 Pipeline B（分诊）和 Pipeline C（分析）。

## 安装

```bash
# 安装 OpenCode CLI
npm install -g @anthropic/opencode

# 或用 Homebrew
brew install opencode
```

## 启动 Server

```bash
# 启动 HTTP REST API server
opencode server --port 4096 --host localhost
```

默认监听 `http://localhost:4096`，Basic Auth 认证。

## 环境变量

在 `.env` 中配置：

```bash
OPENCODE_HOST=localhost
OPENCODE_PORT=4096
OPENCODE_USER=user
OPENCODE_PASS=changeme
OPENCODE_MODEL_CHAIN=claude-sonnet-4-20250514,anthropic:claude-sonnet-4-20250514
```

`MODEL_CHAIN` 支持 fallback：第一个模型不可用时自动切换到下一个。

## API 调用方式

```bash
# 健康检查
curl -u user:changeme http://localhost:4096/health

# 发送任务
curl -u user:changeme -X POST http://localhost:4096/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Triage this issue: ...", "model": "claude-sonnet-4-20250514"}'
```

Python 客户端参考 rootgrove `periodic_jobs/ai_heartbeat/src/v0/opencode_client.py`。

## 与 launchd 集成

Observer 和 Triage Agent 通过 launchd 定时调用 OpenCode Server：

```bash
# 安装定时任务
bash launchd/install.sh
```

定时任务通过 `scripts/` 下的 wrapper 脚本调用 OpenCode API。

## Android 远程访问

若需从 Android 设备访问 OpenCode Server（如通过 Termux），需配置 SSH 隧道：

```bash
# 在 Android 端
ssh -L 4096:localhost:4096 user@your-mac-ip
```

详细隧道诊断见 rootgrove `rules/skills/workflow_opencode_ops.md`。

## 故障排查

- **连接拒绝**: 检查 server 是否在运行 (`lsof -i :4096`)
- **认证失败**: 确认 `.env` 中的 USER/PASS 与 server 启动参数一致
- **模型不可用**: 检查 API key 配置，或切换 MODEL_CHAIN 中的 fallback 模型
- **超时**: OpenCode 默认 120s 超时，复杂分析可能需要调大
