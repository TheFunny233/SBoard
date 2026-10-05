# SBoard

SBoard 是面向个人和小团队的轻量化多节点代理管理平台。项目采用前后端分离结构：

```text
SBoard/
├─ backend/   FastAPI + SQLAlchemy + SQLite
├─ frontend/  Vue 3 + TypeScript + Element Plus
└─ compose.yaml
```

项目不包含用户系统、支付系统、复杂 RBAC、Redis、Kubernetes 或微服务。

## 已实现功能

- SBoardNode Agent 创建、手工 Token 配置、状态与心跳
- 托管节点和外部节点统一管理
- 节点分组与标签
- VLESS、VMess、Trojan、Shadowsocks、Shadowsocks 2022、Hysteria2、TUIC 链接导入
- Clash Meta YAML 与 V2Ray Base64 订阅
- Clash Meta 站点分流规则，支持指定节点、直连、拒绝和常用站点模板
- WireGuard 数据模型预留
- Notion 风格管理界面，使用左侧导航和低饱和中性配色

## 本地开发

### 后端

需要 Python 3.11 或更高版本。

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e "./backend[dev]"
cd backend
../.venv/Scripts/python -m sboard
```

后端默认监听 `http://0.0.0.0:8000`，本机可通过 `http://127.0.0.1:8000` 访问，OpenAPI 文档位于 `/docs`。

开发环境的默认管理 Token 是 `sboard-development-token`。生产环境必须配置至少 32 字符的 `SBOARD_ADMIN_TOKEN`。

### 前端

需要 Node.js 20 或更高版本。

```bash
cd frontend
npm install
npm run dev
```

打开 `http://127.0.0.1:5173`，进入“设置”页粘贴后端管理 Token。Vite 会将 `/api`、`/health` 和 `/subscribe` 代理到本地后端。

## Docker 部署

Docker 只部署中心面板 SBoard，SBoardNode 仍然使用纯 Alpine Linux 上的单二进制文件。

PowerShell：

```powershell
$env:SBOARD_ADMIN_TOKEN = "至少32字符的随机字符串"
docker compose up -d --build
```

启动后：

- 管理界面：`http://127.0.0.1:8080`
- 后端 API：`http://127.0.0.1:8000`，仅绑定本机
- SQLite：保存在 `sboard-data` Docker volume

前端 Nginx 会同源代理 API 和订阅请求，并对含 Token 的 `/subscribe/` 路径关闭访问日志。

## API 范围

- 管理 API：`/api/v1/*`
- Agent 心跳：`POST /api/node/v1/heartbeat`
- Clash 订阅：`GET /subscribe/clash/{token}`
- V2Ray 订阅：`GET /subscribe/v2ray/{token}`

创建 Agent 后，响应只显示一次明文 Agent Token。管理员需要手动将 `server_url`、`node_id` 和 `token` 写入 SBoardNode 配置文件。

## 验证

```bash
cd backend
../.venv/Scripts/pytest

cd ../frontend
npm run build
```
