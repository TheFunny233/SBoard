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
- 节点启用 / 停用、分组与标签
- 每个分组独立配置手动选择、自动测速（url-test）或故障转移（fallback）
- VLESS、VMess、Trojan、Shadowsocks、Shadowsocks 2022、Hysteria2、TUIC 链接导入
- Clash Meta YAML 与 V2Ray Base64 订阅
- 手动配置 Clash Meta 站点分流规则，支持指定节点、节点组、直连与拒绝
- WireGuard 数据模型预留
- Notion 风格管理界面，使用左侧导航和低饱和中性配色

## 节点与分流配置

1. 在“节点”列表直接切换“启用”开关。停用后，节点会从 Clash / V2Ray 订阅及所有策略组中移除，保留节点资料和分组关系，重新启用即可恢复。客户端需要刷新订阅；此开关不停止服务器上的 Xray 进程。
2. 在“分组与标签”编辑 AI、大流量等组，分别选择“自动测速”或“故障转移”，并设置测速地址、间隔与切换容差。新建分组时也可设置。已有分组升级后保持原来的手动策略。
3. 在“规则”点击“添加规则”，手动填写匹配条件，并选择目标节点、节点组、DIRECT 或 REJECT。可设置优先级、启用或停用规则集；数值越小越先匹配。
4. 更新客户端的 Clash Meta 订阅。各策略组只使用自身已启用且被当前订阅包含的成员；组为空时跳过对应规则，并在订阅预览中给出警告，流量继续匹配后续规则。

面板不提供内置推荐规则或自动应用预设。以前已保存的规则会保留，可在规则列表中手动编辑、停用或删除。
手动规则支持 `DOMAIN-SUFFIX`、`GEOSITE`、`GEOIP` 等类型。条件里只写匹配部分，例如 `GEOSITE,category-porn`，目标由面板自动附加；规则行为取决于你配置的顺序和目标。
含 `GEOSITE` 的 Clash Meta 订阅会指定 MetaCubeX 完整 `geosite.dat` 数据源并开启每 24 小时自动更新。
如果客户端已有精简版数据库并提示分类不存在，请在客户端更新 Geo 数据；部分客户端会覆盖订阅中的 GEO 设置，需要检查客户端自己的数据源。

自动测速在客户端执行，选择依据是连接延迟，不是下载带宽或 AI 解锁结果；AI 组仍需分配可用的纯净节点。
策略字段遵循 [Mihomo url-test](https://wiki.metacubex.one/en/config/proxy-groups/url-test/) 与 [fallback](https://wiki.metacubex.one/en/config/proxy-groups/fallback/) 配置。
上述策略与规则仅写入 Clash Meta YAML，V2Ray Base64 格式只包含启用节点的分享链接。

启动时会自动补充现有 SQLite 数据库所需的兼容字段，无需重建数据库。

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
`sboard` 单容器镜像。服务器不运行 Watchtower，更新由 1Panel 手动或计划任务控制。
首次发布后，在 GitHub 仓库的 **Packages** 中将这个容器包设置为 Public；如果保持 Private，
需要在服务器执行 `docker login ghcr.io` 后再拉取镜像。

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
