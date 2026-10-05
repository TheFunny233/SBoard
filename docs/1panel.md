# SBoard 在 1Panel 上用 Docker 部署

本文是在 Linux 服务器上操作，不依赖本地电脑。SBoard 包含 backend 和 frontend 两个容器。backend 只在 Docker 内部网络提供 API，frontend 只绑定服务器本机的 127.0.0.1:23456。公网访问统一通过 1Panel 网站反向代理和 HTTPS。

## 1. 准备服务器

准备一台可 SSH 登录的 Linux 服务器（建议 Ubuntu 22.04/24.04 或 Debian 12），并把域名（例如 sboard.example.com）解析到服务器公网 IP。云安全组和服务器防火墙放行 80/tcp、443/tcp。

如果尚未安装 1Panel，在服务器 SSH 终端执行：

    curl -sSL https://resource.fit2cloud.com/1panel/package/quick_start.sh -o quick_start.sh
    sudo bash quick_start.sh

登录 1Panel 后，在「面板设置」确认 Docker 正常运行。

## 2. 上传项目到服务器

推荐在服务器执行：

    sudo mkdir -p /opt/sboard
    sudo chown -R "$USER":"$USER" /opt/sboard
    cd /opt/sboard
    git clone <你的 SBoard 仓库地址> .

也可以使用 1Panel 文件管理器上传并解压。最终必须存在：

    /opt/sboard/compose.1panel.yaml
    /opt/sboard/backend/
    /opt/sboard/frontend/

## 3. 生成管理 Token

在服务器执行：

    cd /opt/sboard
    openssl rand -hex 32

复制输出结果，作为生产环境的 SBOARD_ADMIN_TOKEN。不要使用开发 Token，也不要提交到 Git。

## 4. 在 1Panel 创建编排

打开「容器」→「编排」→「创建编排」：

1. 名称：sboard。
2. 编排路径：/opt/sboard。
3. 编排文件：compose.1panel.yaml（仓库已提供）。
4. 环境变量添加 SBOARD_ADMIN_TOKEN，值为上一步生成的随机字符串。
5. 保存并启动。首次启动会构建镜像，可能需要几分钟。

服务器终端也可执行：

    cd /opt/sboard
    SBOARD_ADMIN_TOKEN='替换为你的随机字符串' docker compose -f compose.1panel.yaml up -d --build

验证：

    cd /opt/sboard
    docker compose -f compose.1panel.yaml ps
    curl -fsS http://127.0.0.1:23456/health

curl 应返回包含 status 为 ok 的 JSON。日志命令：

    docker compose -f compose.1panel.yaml logs --tail=200 backend frontend

数据库保存在 Docker volume sboard_sboard-data 中。不要执行 docker compose down -v，否则会删除数据库。

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

## 7. 更新与备份

更新代码：

    cd /opt/sboard
    git pull
    docker compose -f compose.1panel.yaml up -d --build

备份数据库：

    mkdir -p /opt/sboard-backup
    docker run --rm -v sboard_sboard-data:/data:ro -v /opt/sboard-backup:/backup alpine:3.20 cp /data/sboard.db /backup/sboard-$(date +%F-%H%M%S).db

排障顺序：先看 docker compose ps，再 curl 本机 health；然后检查 DNS、云安全组、1Panel 防火墙和网站日志。
