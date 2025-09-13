# 🚀 デプロイメントガイド

Local Web Transcriber の本番環境デプロイメント手順

## 📋 **目次**

1. [事前準備](#事前準備)
2. [サーバー設定](#サーバー設定)
3. [SSL/TLS設定](#ssltls設定)
4. [本番デプロイ](#本番デプロイ)
5. [監視設定](#監視設定)
6. [バックアップ戦略](#バックアップ戦略)
7. [トラブルシューティング](#トラブルシューティング)

## 🔧 **事前準備**

### **システム要件**

#### **最小要件**
- Ubuntu 20.04 LTS / CentOS 8+ / Amazon Linux 2
- RAM: 4GB以上
- Storage: 20GB以上
- CPU: 2コア以上

#### **推奨要件**
- RAM: 8GB以上（large モデル使用時は16GB+）
- Storage: 50GB以上（SSD推奨）
- CPU: 4コア以上（AVX2対応）
- GPU: CUDA対応（オプション）

### **必要なソフトウェア**

```bash
# Docker & Docker Compose のインストール
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Docker Compose v2
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# 必要なツール
sudo apt update
sudo apt install -y curl wget git make ufw fail2ban
```

## 🖥️ **サーバー設定**

### **1. ファイアウォール設定**

```bash
# UFW設定
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
```

### **2. Fail2ban設定**

```bash
# Fail2ban設定
sudo cp /etc/fail2ban/jail.conf /etc/fail2ban/jail.local

# SSH保護
sudo tee /etc/fail2ban/jail.d/ssh.conf << EOF
[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 3600
EOF

sudo systemctl restart fail2ban
```

### **3. システム最適化**

```bash
# スワップファイル作成（RAM不足対策）
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# ファイル制限の調整
echo '*               soft    nofile          65536' | sudo tee -a /etc/security/limits.conf
echo '*               hard    nofile          65536' | sudo tee -a /etc/security/limits.conf

# カーネルパラメータ調整
sudo tee -a /etc/sysctl.conf << EOF
fs.file-max = 65536
net.core.rmem_max = 134217728
net.core.wmem_max = 134217728
net.ipv4.tcp_rmem = 4096 16384 134217728
net.ipv4.tcp_wmem = 4096 65536 134217728
EOF

sudo sysctl -p
```

## 🔐 **SSL/TLS設定**

### **Let's Encrypt使用（推奨）**

```bash
# Certbot インストール
sudo apt install -y certbot python3-certbot-nginx

# ドメイン設定（example.comを実際のドメインに変更）
export DOMAIN="your-domain.com"
export EMAIL="your-email@example.com"

# 証明書取得
sudo certbot certonly \
  --standalone \
  -d $DOMAIN \
  --email $EMAIL \
  --agree-tos \
  --non-interactive

# 証明書をコピー
sudo cp /etc/letsencrypt/live/$DOMAIN/fullchain.pem nginx/ssl/cert.pem
sudo cp /etc/letsencrypt/live/$DOMAIN/privkey.pem nginx/ssl/key.pem
sudo chown $(id -u):$(id -g) nginx/ssl/*.pem
```

### **自動更新設定**

```bash
# 自動更新スクリプト
sudo tee /usr/local/bin/renew-cert.sh << 'EOF'
#!/bin/bash
certbot renew --quiet
if [ $? -eq 0 ]; then
    cp /etc/letsencrypt/live/*/fullchain.pem /path/to/project/nginx/ssl/cert.pem
    cp /etc/letsencrypt/live/*/privkey.pem /path/to/project/nginx/ssl/key.pem
    chown $(id -u):$(id -g) /path/to/project/nginx/ssl/*.pem
    cd /path/to/project && docker-compose restart nginx
fi
EOF

sudo chmod +x /usr/local/bin/renew-cert.sh

# Cron設定
echo "0 3 * * * /usr/local/bin/renew-cert.sh" | sudo crontab -
```

## 🚀 **本番デプロイ**

### **1. アプリケーション設定**

```bash
# プロジェクトクローン
git clone https://github.com/yourusername/local-web-transcriber-improved.git
cd local-web-transcriber-improved

# 本番環境設定
cp .env.template .env
```

### **2. 環境変数設定**

```bash
# .env ファイル編集
cat > .env << EOF
# === 本番設定 ===
MODEL_ID=base
COMPUTE_TYPE=int8
DEFAULT_LANGUAGE=ja
DEFAULT_TASK=transcribe
MAX_WORKERS=4
MEMORY_LIMIT=6G
CPU_LIMIT=4.0

# === セキュリティ ===
MAX_FILE_SIZE=524288000
FILE_RETENTION_HOURS=6

# === 監視 ===
ENABLE_MONITORING=true
ENABLE_LOGGING=true

# === ネットワーク ===
HOST_PORT=7860
NGINX_PORT=80
NGINX_SSL_PORT=443
EOF
```

### **3. アプリケーション起動**

```bash
# 初期設定
make setup

# デプロイ前チェック
make deploy-check

# ビルド・起動
make build
make run-monitoring

# ヘルスチェック
make health-check
```

### **4. 起動確認**

```bash
# サービス状態確認
make status

# ログ確認
make logs | head -50

# エンドポイントテスト
curl -f http://localhost/health
curl -f https://your-domain.com/health
```

## 📊 **監視設定**

### **1. Prometheus設定**

```yaml
# monitoring/prometheus.yml
global:
  scrape_interval: 15s
  
scrape_configs:
  - job_name: 'transcriber'
    static_configs:
      - targets: ['transcriber:7860']
    metrics_path: '/metrics'
    scrape_interval: 30s
    
  - job_name: 'nginx'
    static_configs:
      - targets: ['nginx:9113']
```

### **2. ログ設定**

```bash
# ログ監視設定
sudo tee /etc/logrotate.d/transcriber << EOF
/path/to/project/logs/nginx/*.log {
    daily
    missingok
    rotate 7
    compress
    notifempty
    copytruncate
}

/path/to/project/data/logs/*.json {
    daily
    missingok
    rotate 14
    compress
    notifempty
    copytruncate
}
EOF
```

### **3. アラート設定**

```bash
# システム監視スクリプト
sudo tee /usr/local/bin/monitor-transcriber.sh << 'EOF'
#!/bin/bash

# ヘルスチェック
if ! curl -f -s http://localhost/health > /dev/null; then
    echo "$(date): Health check failed" >> /var/log/transcriber-monitor.log
    # 必要に応じてSlack/メール通知
fi

# ディスク使用量チェック
USAGE=$(df /path/to/project/data | tail -1 | awk '{print $5}' | sed 's/%//')
if [ $USAGE -gt 80 ]; then
    echo "$(date): Disk usage high: $USAGE%" >> /var/log/transcriber-monitor.log
fi

# メモリ使用量チェック
MEM_USAGE=$(free | grep Mem | awk '{printf "%.0f", $3/$2 * 100.0}')
if [ $MEM_USAGE -gt 85 ]; then
    echo "$(date): Memory usage high: $MEM_USAGE%" >> /var/log/transcriber-monitor.log
fi
EOF

sudo chmod +x /usr/local/bin/monitor-transcriber.sh

# 5分毎に実行
echo "*/5 * * * * /usr/local/bin/monitor-transcriber.sh" | sudo crontab -
```

## 💾 **バックアップ戦略**

### **1. データバックアップ**

```bash
# 自動バックアップスクリプト
sudo tee /usr/local/bin/backup-transcriber.sh << 'EOF'
#!/bin/bash

PROJECT_PATH="/path/to/project"
BACKUP_PATH="/backup/transcriber"
DATE=$(date +%Y%m%d_%H%M%S)

# バックアップディレクトリ作成
mkdir -p $BACKUP_PATH

# データバックアップ
cd $PROJECT_PATH
make backup

# リモートバックアップ（S3など）
# aws s3 sync backups/ s3://your-backup-bucket/transcriber/

# 古いバックアップ削除（7日以上古いもの）
find $PROJECT_PATH/backups -name "*.tar.gz" -mtime +7 -delete

echo "$(date): Backup completed" >> /var/log/backup.log
EOF

sudo chmod +x /usr/local/bin/backup-transcriber.sh

# 毎日午前3時に実行
echo "0 3 * * * /usr/local/bin/backup-transcriber.sh" | sudo crontab -
```

### **2. システムバックアップ**

```bash
# システム設定バックアップ
sudo tee /usr/local/bin/system-backup.sh << 'EOF'
#!/bin/bash

BACKUP_DIR="/backup/system/$(date +%Y%m%d)"
mkdir -p $BACKUP_DIR

# 重要な設定ファイルをバックアップ
cp -r /etc/nginx $BACKUP_DIR/
cp -r /etc/ssl $BACKUP_DIR/
cp /etc/crontab $BACKUP_DIR/
cp -r /etc/fail2ban $BACKUP_DIR/

tar -czf $BACKUP_DIR/../system-$(date +%Y%m%d).tar.gz -C $BACKUP_DIR .
rm -rf $BACKUP_DIR
EOF
```

## 🎯 **パフォーマンス最適化**

### **1. Nginx最適化**

```nginx
# nginx/nginx.conf
worker_processes auto;
worker_rlimit_nofile 65535;

events {
    worker_connections 1024;
    use epoll;
    multi_accept on;
}

http {
    # 基本設定
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    
    # Gzip圧縮
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types
        text/plain
        text/css
        text/xml
        text/javascript
        application/json
        application/javascript
        application/xml+rss
        application/atom+xml;
    
    # バッファサイズ
    client_body_buffer_size 128k;
    client_max_body_size 500m;
    client_header_buffer_size 1k;
    large_client_header_buffers 4 4k;
    output_buffers 1 32k;
    postpone_output 1460;
}
```

### **2. システムリソース最適化**

```bash
# Docker Composeリソース制限
# docker-compose.yml で以下を設定
deploy:
  resources:
    limits:
      memory: 6G
      cpus: 4.0
    reservations:
      memory: 2G
      cpus: 1.0
```

## 🔍 **トラブルシューティング**

### **よくある問題と解決法**

#### **1. SSL証明書エラー**
```bash
# 証明書確認
sudo certbot certificates

# 証明書再取得
sudo certbot delete --cert-name your-domain.com
sudo certbot certonly --standalone -d your-domain.com

# 権限修正
sudo chown $(id -u):$(id -g) nginx/ssl/*.pem
```

#### **2. メモリ不足**
```bash
# スワップ使用量確認
free -h

# 不要なDockerイメージ削除
docker system prune -af

# メモリ使用量の多いプロセス確認
docker stats
```

#### **3. ディスク容量不足**
```bash
# 古いログ削除
make clean-data

# Docker領域確認
docker system df

# 古いバックアップ削除
find backups/ -mtime +7 -delete
```

#### **4. 接続問題**
```bash
# ファイアウォール確認
sudo ufw status

# ポート確認
sudo netstat -tulpn | grep :80
sudo netstat -tulpn | grep :443

# Nginxログ確認
tail -f logs/nginx/transcriber_error.log
```

### **緊急時対応**

```bash
# 緊急停止
make emergency-stop

# システム復旧
make recovery

# ログ確認
make logs | grep ERROR

# バックアップからの復旧
make restore BACKUP_FILE=backups/backup_20231201_030000.tar.gz
```

## 📈 **スケーリング**

### **水平スケーリング**

```yaml
# docker-compose.scale.yml
version: '3.8'
services:
  transcriber:
    deploy:
      replicas: 3
  
  nginx:
    depends_on:
      - transcriber
    deploy:
      replicas: 1
```

### **負荷分散**

```bash
# 複数インスタンス起動
docker-compose up --scale transcriber=3
```

---

**🚀 本番環境での安全で高性能な運用を実現！**
