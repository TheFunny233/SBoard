# SBoard 在 1Panel 上用 Docker 部署

本文是在 Linux 服务器上操作，不依赖本地电脑。SBoard 包含 backend 和 frontend 两个容器。backend 只在 Docker 内部网络提供 API，frontend 只绑定服务器本机的 127.0.0.1:23456。公网访问统一通过 1Panel 网站反向代理和 HTTPS。

## 1. 准备服务器

准备一台可 SSH 登录的 Linux 服务器（建议 Ubuntu 22.04/24.04 或 Debian 12），并把域名（例如 sboard.example.com）解析到服务器公网 IP。云安全组和服务器防火墙放行 80/tcp、443/tcp。

如果尚未安装 1Panel，在服务器 SSH 终端执行：

    curl -sSL https://resource.fit2cloud.com/1panel/package/quick_start.sh -o quick_start.sh
    sudo bash quick_start.sh

登录 1Panel 后，在「面板设置」确认 Docker 正常运行。

## 2. 不需要上传项目目录

当前部署使用 GitHub Packages（GHCR）中的现成镜像，Compose 文件里没有 `build:`，因此不需要上传或克隆整个 SBoard 项目，也不需要上传 `backend/`、`frontend/` 源码目录。你只需要把一个 Compose 文件交给 1Panel。

可以直接在 1Panel 编排编辑器中粘贴仓库里的 [compose.1panel.yaml](https://raw.githubusercontent.com/TheFunny233/SBoard/main/compose.1panel.yaml)。如果使用服务器终端，只下载这一个文件即可：

    sudo mkdir -p /opt/sboard
    cd /opt/sboard
    curl -fsSL https://raw.githubusercontent.com/TheFunny233/SBoard/main/compose.1panel.yaml -o compose.yaml

## 3. 生成管理 Token

在服务器执行：

    cd /opt/sboard
    openssl rand -hex 32

复制输出结果，作为生产环境的 SBOARD_ADMIN_TOKEN。不要使用开发 Token，也不要提交到 Git。

## 4. 在 1Panel 创建编排

打开「容器」→「编排」→「创建编排」：

1. 名称：sboard。
2. 编排内容：粘贴 `compose.1panel.yaml` 的完整内容。不要选择本地源码目录，也不要执行构建。
3. 环境变量添加 `SBOARD_ADMIN_TOKEN`，值为上一步生成的随机字符串。
4. 保存并启动。首次启动会从 GHCR 拉取镜像，可能需要几分钟。

服务器终端也可执行：

    cd /opt/sboard
    printf 'SBOARD_ADMIN_TOKEN=%s\n' '替换为你的随机字符串' > .env
    docker compose -f compose.yaml up -d

验证：

    cd /opt/sboard
    docker compose -f compose.yaml ps
    curl -fsS http://127.0.0.1:23456/health

curl 应返回包含 status 为 ok 的 JSON。日志命令：

    docker compose -f compose.yaml logs --tail=200 backend frontend watchtower

数据库保存在 Docker volume sboard-data 中。不要执行 docker compose down -v，否则会删除数据库。

## 5. 配置公网访问

在 1Panel 打开「网站」→「创建网站」→「反向代理」：

1. 域名填写你的实际域名，例如 sboard.example.com。
2. 代理地址填写 http://127.0.0.1:23456。
3. 申请 Let's Encrypt SSL 证书并开启强制 HTTPS。
4. 网站反向代理配置至少包含：

    location ^~ / {
        proxy_pass http://127.0.0.1:23456;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 60s;
        proxy_buffering off;
    }

公网只开放 80/443。compose.1panel.yaml 没有发布 8000，23456 仅绑定 127.0.0.1，不要在云安全组开放它们。

## 6. 首次登录和节点

浏览器打开 https://你的域名，在「设置」页粘贴同一个 SBOARD_ADMIN_TOKEN。创建 SBoardNode Agent 后，节点的 server_url 使用：

    https://你的域名

订阅地址：

    https://你的域名/subscribe/clash/<订阅Token>
    https://你的域名/subscribe/v2ray/<订阅Token>

## 7. 自动更新、手动更新与备份

仓库中的 `.github/workflows/publish-images.yml` 会在 `main` 分支每次推送后，把前后端镜像发布到 GitHub Packages：

    ghcr.io/thefunny233/sboard-backend:latest
    ghcr.io/thefunny233/sboard-frontend:latest

首次发布后，请在 GitHub 仓库的「Packages」中将两个容器包设置为 Public，否则服务器无法匿名拉取。当前 Compose 按公开包设计；如果必须使用 Private 包，需要另外为 Watchtower 配置 GHCR 登录凭据。`watchtower` 容器每 5 分钟检查一次这两个带有更新标签的服务，发现新镜像后会自动拉取、替换容器并保留 SQLite volume。

手动立即更新：

    cd /opt/sboard
    docker compose -f compose.yaml pull
    docker compose -f compose.yaml up -d

备份数据库：

    mkdir -p /opt/sboard-backup
    docker run --rm -v sboard-data:/data:ro -v /opt/sboard-backup:/backup alpine:3.20 cp /data/sboard.db /backup/sboard-$(date +%F-%H%M%S).db

排障顺序：先看 docker compose ps，再 curl 本机 health；然后检查 DNS、云安全组、1Panel 防火墙和网站日志。
