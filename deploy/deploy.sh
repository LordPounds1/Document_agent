#!/bin/bash
# ===========================================
# Скрипт развёртывания Document Processing Agent на VPS
# ===========================================
# 
# Использование:
#   chmod +x deploy.sh
#   sudo ./deploy.sh YOUR_DOMAIN
#
# Пример:
#   sudo ./deploy.sh docs.example.com

set -e  # Остановка при ошибке

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Проверка root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}❌ Запустите скрипт с sudo${NC}"
    exit 1
fi

# Проверка аргументов
DOMAIN=$1
if [ -z "$DOMAIN" ]; then
    echo -e "${RED}❌ Укажите домен: sudo ./deploy.sh YOUR_DOMAIN${NC}"
    exit 1
fi

echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}🚀 Document Processing Agent - Deploy${NC}"
echo -e "${GREEN}=========================================${NC}"
echo -e "Домен: ${YELLOW}$DOMAIN${NC}"
echo ""

# ===========================================
# 1. Обновление системы
# ===========================================
echo -e "${YELLOW}📦 Обновление системы...${NC}"
apt-get update && apt-get upgrade -y

# ===========================================
# 2. Установка Docker
# ===========================================
echo -e "${YELLOW}🐳 Установка Docker...${NC}"

if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    rm get-docker.sh
    
    # Docker Compose
    apt-get install -y docker-compose-plugin
    
    # Добавляем текущего пользователя в группу docker
    usermod -aG docker $SUDO_USER || true
    
    echo -e "${GREEN}✅ Docker установлен${NC}"
else
    echo -e "${GREEN}✅ Docker уже установлен${NC}"
fi

# ===========================================
# 3. Установка Nginx
# ===========================================
echo -e "${YELLOW}🌐 Установка Nginx...${NC}"

apt-get install -y nginx certbot python3-certbot-nginx

# ===========================================
# 4. Настройка Firewall
# ===========================================
echo -e "${YELLOW}🔥 Настройка UFW Firewall...${NC}"

ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 'Nginx Full'
ufw --force enable

echo -e "${GREEN}✅ Firewall настроен (SSH, HTTP, HTTPS)${NC}"

# ===========================================
# 5. Создание директории приложения
# ===========================================
APP_DIR="/opt/document-agent"
echo -e "${YELLOW}📁 Создание директории $APP_DIR...${NC}"

mkdir -p $APP_DIR
mkdir -p $APP_DIR/models
mkdir -p $APP_DIR/templates
mkdir -p $APP_DIR/data
mkdir -p $APP_DIR/logs

# ===========================================
# 6. Настройка Nginx
# ===========================================
echo -e "${YELLOW}⚙️ Настройка Nginx...${NC}"

# Копируем конфиг
cat > /etc/nginx/sites-available/document-agent << 'NGINX_EOF'
# Rate limiting
limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m;
limit_req_zone $binary_remote_addr zone=api:10m rate=30r/m;

upstream streamlit_app {
    server 127.0.0.1:8501;
    keepalive 32;
}

server {
    listen 80;
    server_name DOMAIN_PLACEHOLDER;
    
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }
    
    location / {
        return 301 https://$server_name$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name DOMAIN_PLACEHOLDER;
    
    ssl_certificate /etc/letsencrypt/live/DOMAIN_PLACEHOLDER/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/DOMAIN_PLACEHOLDER/privkey.pem;
    
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:50m;
    
    add_header Strict-Transport-Security "max-age=63072000" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    location / {
        limit_req zone=api burst=20 nodelay;
        
        proxy_pass http://streamlit_app;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        proxy_read_timeout 300s;
        proxy_buffering off;
    }
    
    location /_stcore/stream {
        proxy_pass http://streamlit_app/_stcore/stream;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400s;
    }
    
    client_max_body_size 50M;
    
    access_log /var/log/nginx/document-agent.access.log;
    error_log /var/log/nginx/document-agent.error.log;
}
NGINX_EOF

# Заменяем placeholder на реальный домен
sed -i "s/DOMAIN_PLACEHOLDER/$DOMAIN/g" /etc/nginx/sites-available/document-agent

# Активируем сайт
ln -sf /etc/nginx/sites-available/document-agent /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Создаём директорию для certbot
mkdir -p /var/www/certbot

# ===========================================
# 7. Получение SSL сертификата
# ===========================================
echo -e "${YELLOW}🔒 Получение SSL сертификата Let's Encrypt...${NC}"

# Временно запускаем nginx для получения сертификата
# Сначала создаём временный конфиг только для HTTP
cat > /etc/nginx/sites-available/document-agent-temp << EOF
server {
    listen 80;
    server_name $DOMAIN;
    
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }
    
    location / {
        return 200 'OK';
        add_header Content-Type text/plain;
    }
}
EOF

ln -sf /etc/nginx/sites-available/document-agent-temp /etc/nginx/sites-enabled/document-agent
nginx -t && systemctl restart nginx

# Получаем сертификат
certbot certonly --webroot -w /var/www/certbot -d $DOMAIN --non-interactive --agree-tos --email admin@$DOMAIN || {
    echo -e "${YELLOW}⚠️ Не удалось получить сертификат автоматически.${NC}"
    echo -e "${YELLOW}Запустите вручную: sudo certbot --nginx -d $DOMAIN${NC}"
}

# Возвращаем основной конфиг
ln -sf /etc/nginx/sites-available/document-agent /etc/nginx/sites-enabled/document-agent
rm -f /etc/nginx/sites-available/document-agent-temp

# Проверяем и перезапускаем nginx
nginx -t && systemctl restart nginx

echo -e "${GREEN}✅ SSL настроен${NC}"

# ===========================================
# 8. Автообновление сертификата
# ===========================================
echo -e "${YELLOW}🔄 Настройка автообновления сертификата...${NC}"

# Добавляем cron задачу
(crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet --post-hook 'systemctl reload nginx'") | crontab -

# ===========================================
# 9. Создание docker-compose для продакшена
# ===========================================
echo -e "${YELLOW}🐳 Создание docker-compose.prod.yml...${NC}"

cat > $APP_DIR/docker-compose.prod.yml << 'EOF'
services:
  document-agent:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: document-agent
    restart: always
    ports:
      - "127.0.0.1:8501:8501"  # Только localhost (nginx проксирует)
    volumes:
      - ./models:/app/models:ro
      - ./templates:/app/templates:ro
      - ./data:/app/data
      - ./logs:/app/logs
    environment:
      - MODEL_CONTEXT_SIZE=2048
      - MODEL_TEMPERATURE=0.1
      - MODEL_N_GPU_LAYERS=0
      - MODEL_MAX_TOKENS=512
      - CHECK_INTERVAL_MINUTES=5
      - LOG_LEVEL=INFO
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8501/_stcore/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
EOF

# ===========================================
# 10. Финальные инструкции
# ===========================================
echo ""
echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}✅ Базовая настройка завершена!${NC}"
echo -e "${GREEN}=========================================${NC}"
echo ""
echo -e "${YELLOW}📋 Следующие шаги:${NC}"
echo ""
echo "1. Скопируйте файлы проекта в $APP_DIR:"
echo -e "   ${GREEN}scp -r ./* user@server:$APP_DIR/${NC}"
echo ""
echo "2. Скопируйте модель в $APP_DIR/models/:"
echo -e "   ${GREEN}scp model-q4_K.gguf user@server:$APP_DIR/models/${NC}"
echo ""
echo "3. Запустите приложение:"
echo -e "   ${GREEN}cd $APP_DIR && docker compose -f docker-compose.prod.yml up -d --build${NC}"
echo ""
echo "4. Проверьте работу:"
echo -e "   ${GREEN}https://$DOMAIN${NC}"
echo ""
echo -e "${YELLOW}📊 Полезные команды:${NC}"
echo "  - Логи: docker logs -f document-agent"
echo "  - Статус: docker ps"
echo "  - Перезапуск: docker compose -f docker-compose.prod.yml restart"
echo ""
