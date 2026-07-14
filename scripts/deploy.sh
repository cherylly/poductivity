#!/bin/bash
set -e

echo "=== Content Digest 云服务器部署脚本 ==="
echo ""

# Step 1: 安装 Docker
echo "[1/6] 安装 Docker..."
if command -v docker &> /dev/null; then
    echo "Docker 已安装, 跳过"
else
    dnf install -y docker || yum install -y docker
    systemctl start docker
    systemctl enable docker
fi
docker --version

# Step 2: 安装 Docker Compose
echo ""
echo "[2/6] 安装 Docker Compose..."
if command -v docker-compose &> /dev/null; then
    echo "Docker Compose 已安装, 跳过"
else
    curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
fi
docker-compose --version || echo "Docker Compose plugin: $(docker compose version)"

# Step 3: 安装 Git
echo ""
echo "[3/6] 安装 Git..."
if command -v git &> /dev/null; then
    echo "Git 已安装, 跳过"
else
    dnf install -y git || yum install -y git
fi
git --version

# Step 4: 克隆代码
echo ""
echo "[4/6] 克隆代码..."
APP_DIR="/opt/content-digest"
if [ -d "$APP_DIR" ]; then
    echo "代码目录已存在, 拉取最新代码"
    cd "$APP_DIR" && git pull
else
    git clone https://github.com/cherylly/poductivity.git "$APP_DIR"
    cd "$APP_DIR"
fi

# Step 5: 配置环境变量
echo ""
echo "[5/6] 配置环境变量..."
if [ ! -f "$APP_DIR/.env" ]; then
    echo "请手动创建 .env 文件, 参考 .env 模板"
    echo "现在创建一个基础的 .env 文件..."
    cat > "$APP_DIR/.env" << 'ENVEOF'
# LLM API - 替换为你的 API 配置
ANTHROPIC_AUTH_TOKEN=YOUR_TOKEN_HERE
LLM_BASE_URL=https://api.example.com/v1
LLM_MODEL=glm-5.1

# Web
WEB_BASE_URL=http://0.0.0.0:8080
WEB_HOST=0.0.0.0
WEB_PORT=8080

# Groq Whisper - 注册 https://console.groq.com 获取
GROQ_API_KEY=YOUR_GROQ_API_KEY
GROQ_WHISPER_MODEL=whisper-large-v3-turbo

# Schedule
DIGEST_CRON_HOUR=2
DIGEST_CRON_MINUTE=0
ENVEOF
    echo ".env 文件已创建"
else
    echo ".env 文件已存在"
fi

# Step 6: 构建并启动
echo ""
echo "[6/6] 构建并启动服务..."
cd "$APP_DIR"

echo ""
echo "=== 部署完成! ==="
echo "请在腾讯云防火墙中开放 8080 端口"
echo "然后访问: http://$(curl -s ifconfig.me):8080"
