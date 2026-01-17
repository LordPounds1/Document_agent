# 🚀 Руководство по развёртыванию на VPS

## Быстрый старт

### 1. Требования к серверу

| Параметр | Минимум | Рекомендуется |
|----------|---------|---------------|
| CPU | 2 vCPU | 4 vCPU |
| RAM | 8 GB | 16 GB |
| Диск | 20 GB SSD | 50 GB SSD |
| ОС | Ubuntu 22.04 | Ubuntu 22.04 |

### 2. Автоматический деплой

```bash
# На сервере
git clone https://github.com/your-repo/document_processing_agent.git
cd document_processing_agent/deploy

chmod +x deploy.sh
sudo ./deploy.sh your-domain.com
```

### 3. Ручной деплой

#### Установка Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
```

#### Установка Nginx + Certbot

```bash
sudo apt install nginx certbot python3-certbot-nginx
```

#### Получение SSL сертификата

```bash
sudo certbot --nginx -d your-domain.com
```

#### Запуск приложения

```bash
cd /opt/document-agent

# Скопируйте файлы проекта
# Скопируйте модель в ./models/

# Запуск
docker compose -f docker-compose.prod.yml up -d --build
```

---

## 🔐 Безопасность

### Аутентификация

При первом запуске приложение попросит создать учётную запись администратора.

**Сброс пароля:**
```bash
# Удалите файл пользователей
rm .users

# Перезапустите приложение
docker compose -f docker-compose.prod.yml restart
```

### SSL/HTTPS

Используется Let's Encrypt. Сертификаты автоматически обновляются.

**Проверка сертификата:**
```bash
sudo certbot certificates
```

**Принудительное обновление:**
```bash
sudo certbot renew --force-renewal
```

### Firewall

```bash
# Статус
sudo ufw status

# Разрешённые порты: 22 (SSH), 80 (HTTP), 443 (HTTPS)
```

---

## 📊 Мониторинг

### Логи приложения

```bash
# Все логи
docker logs -f document-agent

# Последние 100 строк
docker logs --tail 100 document-agent
```

### Логи Nginx

```bash
sudo tail -f /var/log/nginx/document-agent.access.log
sudo tail -f /var/log/nginx/document-agent.error.log
```

### Статус контейнера

```bash
docker ps
docker stats document-agent
```

---

## 🔄 Обновление

```bash
cd /opt/document-agent

# Остановка
docker compose -f docker-compose.prod.yml down

# Обновление кода
git pull

# Пересборка и запуск
docker compose -f docker-compose.prod.yml up -d --build
```

---

## 🆘 Решение проблем

### Приложение не запускается

```bash
# Проверьте логи
docker logs document-agent

# Проверьте наличие модели
ls -la models/
```

### 502 Bad Gateway

```bash
# Проверьте статус контейнера
docker ps

# Перезапустите
docker compose -f docker-compose.prod.yml restart
```

### Проблемы с памятью

```bash
# Проверьте использование
free -h
docker stats

# Увеличьте swap
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

---

## 📁 Структура на сервере

```
/opt/document-agent/
├── docker-compose.prod.yml
├── Dockerfile
├── .env                    # Переменные окружения
├── .users                  # Файл пользователей (хэши)
├── models/
│   └── model-q4_K.gguf    # LLM модель
├── templates/              # Расшифрованные шаблоны
├── templates_encrypted/    # Зашифрованные шаблоны
├── data/                   # Результаты работы
├── logs/                   # Логи приложения
├── whatsapp_session/       # Сессия WhatsApp (сохраняется)
└── whatsapp_downloads/     # Скачанные документы из WhatsApp
```

---

## 🔗 Полезные ссылки

- [Docker Documentation](https://docs.docker.com/)
- [Nginx SSL Configuration](https://ssl-config.mozilla.org/)
- [Let's Encrypt](https://letsencrypt.org/)
- [Streamlit Deployment](https://docs.streamlit.io/deploy)
