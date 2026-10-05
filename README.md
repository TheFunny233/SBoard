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

Docker 将前端、后端打包在一个 SBoard 容器中，SBoardNode 仍然使用纯 Alpine Linux 上的单二进制文件。

服务器使用 1Panel 部署请直接阅读：[SBoard 在 1Panel 上用 Docker 部署](docs/1panel.md)。该方案通过 1Panel 网站反向代理提供公网 HTTPS 访问，后端端口不会暴露到公网。

PowerShell：

```powershell
$env:SBOARD_ADMIN_TOKEN = "至少32字符的随机字符串"
docker compose up -d --build
```

启动后：

- 管理界面：`http://127.0.0.1:23456`
- 后端 API：由同一容器通过 `http://127.0.0.1:23456/api/` 提供
- SQLite：保存在 `sboard-data` Docker volume

前端 Nginx 会同源代理 API 和订阅请求，并对含 Token 的 `/subscribe/` 路径关闭访问日志。

### 1Panel 公网部署

SBoard 可以直接作为 1Panel 的 Docker Compose 项目运行。建议使用域名访问，
让 1Panel 的网站反向代理负责 HTTPS；不要把容器内部端口暴露到公网。

1. 在服务器安全组/防火墙放行 `80`、`443`。当前 1Panel Compose 将前端绑定到服务器本机的 `127.0.0.1:23456`，不直接暴露管理页面。
2. 1Panel -> **容器** -> **编排** -> **创建编排**，直接粘贴仓库里的 `compose.1panel.yaml`。
   当前方案使用 GHCR 现成的单容器镜像，不需要上传或克隆 `backend/`、`frontend/` 源码目录。
3. 在 Compose 文件同目录创建 `.env`，写入一个随机的 32 字符以上管理 Token：

   ```dotenv
   SBOARD_ADMIN_TOKEN=请替换为随机的长字符串
   ```

   可用 `openssl rand -hex 32` 生成。不要把 Token 提交到 Git 或写进镜像。
4. 使用 `docker compose up -d` 启动。前端默认发布为
   `127.0.0.1:23456 -> 80`，首次拉取镜像可能需要几分钟。
5. 正式使用时，在 1Panel -> **网站** -> **创建网站** 中绑定域名，反向代理到
   `http://127.0.0.1:23456`，申请并启用 Let's Encrypt 证书，然后通过 `https://你的域名` 访问。
   面板中的“代理目录”保持 `/`，并开启 WebSocket（当前版本不依赖 WebSocket，但开启不会有坏处）。
6. 打开“设置”页，粘贴同一个 `SBOARD_ADMIN_TOKEN`。节点的 `server_url` 应填写公网地址，
   例如 `https://sboard.example.com`；订阅地址也使用该域名下的 `/subscribe/...` 路径。

公网部署检查：

```bash
curl https://你的域名/health
docker compose ps
docker compose logs --tail=100 sboard
```

`/health` 返回 `{"status":"ok",...}` 才表示服务已就绪。SQLite 数据位于 Docker volume
`sboard-data`，请在 1Panel 中为该 volume 配置定期备份。管理 Token 一旦泄露应立即在 `.env`
中更换并重建容器；订阅 Token 则在“订阅”页单独轮换。

镜像由 GitHub Actions 自动发布到 GitHub Packages（GHCR）。`main` 分支每次推送后会构建
`sboard` 单容器镜像，服务器上的 Watchtower 每 5 分钟检查并自动重启到新镜像。
首次发布后，在 GitHub 仓库的 **Packages** 中将这个容器包设置为 Public；如果保持 Private，
当前这份 1Panel Compose 无法匿名拉取，不能直接使用。私有包需要另外配置 Watchtower 的 GHCR 登录凭据。

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
