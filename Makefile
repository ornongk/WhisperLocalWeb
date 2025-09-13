# Local Web Transcriber - Makefile
# 開発・運用・デプロイメント支援

.PHONY: help setup build run stop clean test security-check lint format install-dev logs backup restore

# デフォルトターゲット
help: ## ヘルプを表示
	@echo "Local Web Transcriber - 開発・運用支援コマンド"
	@echo "================================================"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ===== 環境設定 =====
setup: ## 初期環境セットアップ
	@echo "🚀 初期環境をセットアップ中..."
	@if [ ! -f .env ]; then cp .env.template .env; echo "✅ .envファイルを作成しました"; fi
	@mkdir -p data/uploads data/outputs data/logs nginx/ssl logs/nginx monitoring
	@chmod 755 data nginx logs monitoring
	@echo "✅ ディレクトリ構造を作成しました"
	@echo "📝 .envファイルを編集して設定を調整してください"

install-dev: ## 開発用依存関係のインストール
	@echo "📦 開発用パッケージをインストール中..."
	pip install -r requirements.txt
	pip install pytest pytest-asyncio httpx black flake8 mypy bandit safety

# ===== Docker操作 =====
build: ## Dockerイメージをビルド
	@echo "🔨 Dockerイメージをビルド中..."
	docker compose build --no-cache

run: ## アプリケーションを起動
	@echo "🚀 アプリケーションを起動中..."
	docker compose up -d
	@echo "✅ アプリケーションが起動しました"
	@echo "🌐 http://localhost:7860 でアクセスできます"

run-dev: ## 開発モードで起動
	@echo "🔧 開発モードで起動中..."
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
	@echo "✅ 開発モードで起動しました"

run-monitoring: ## 監視機能付きで起動
	@echo "📊 監視機能付きで起動中..."
	docker compose --profile monitoring up -d
	@echo "✅ 監視機能付きで起動しました"
	@echo "📊 Prometheus: http://localhost:9090"

stop: ## アプリケーションを停止
	@echo "🛑 アプリケーションを停止中..."
	docker compose down
	@echo "✅ アプリケーションを停止しました"

restart: stop run ## アプリケーションを再起動

# ===== ログ・監視 =====
logs: ## ログを表示
	docker compose logs -f

logs-app: ## アプリケーションログのみ表示
	docker compose logs -f transcriber

logs-nginx: ## Nginxログのみ表示
	docker compose logs -f nginx

status: ## コンテナ状態を確認
	@echo "📊 コンテナ状態:"
	@docker compose ps
	@echo ""
	@echo "💾 ディスク使用量:"
	@du -sh data/
	@echo ""
	@echo "🔍 リソース使用量:"
	@docker stats --no-stream

# ===== テスト・品質チェック =====
test: ## テストを実行
	@echo "🧪 テストを実行中..."
	python -m pytest test_main.py -v --tb=short

test-coverage: ## カバレッジ付きテストを実行
	@echo "🧪 カバレッジ付きテストを実行中..."
	python -m pytest --cov=app --cov-report=html --cov-report=term test_main.py

security-check: ## セキュリティチェックを実行
	@echo "🔒 セキュリティチェックを実行中..."
	@echo "📋 Python依存関係のセキュリティチェック..."
	safety check
	@echo "🔍 コードのセキュリティ解析..."
	bandit -r app/ -f json -o security-report.json || true
	@echo "🔐 Dockerイメージのセキュリティスキャン..."
	docker scout cves local-web-transcriber || echo "Docker Scout not available"
	@echo "✅ セキュリティチェック完了"

lint: ## コード品質チェック
	@echo "🔍 コード品質をチェック中..."
	flake8 app/ --max-line-length=100 --extend-ignore=E203,W503
	mypy app/ --ignore-missing-imports
	@echo "✅ Lintチェック完了"

format: ## コードフォーマット
	@echo "✨ コードをフォーマット中..."
	black app/ --line-length=100
	@echo "✅ フォーマット完了"

# ===== バックアップ・復元 =====
backup: ## データをバックアップ
	@echo "💾 データをバックアップ中..."
	@mkdir -p backups
	@timestamp=$(shell date +%Y%m%d_%H%M%S); \
	tar -czf backups/backup_$$timestamp.tar.gz data/ .env; \
	echo "✅ バックアップ完了: backups/backup_$$timestamp.tar.gz"

restore: ## データを復元（BACKUP_FILE=<ファイル名>で指定）
	@if [ -z "$(BACKUP_FILE)" ]; then \
		echo "❌ エラー: BACKUP_FILE=<ファイル名>を指定してください"; \
		echo "例: make restore BACKUP_FILE=backups/backup_20231201_120000.tar.gz"; \
		exit 1; \
	fi
	@echo "🔄 データを復元中..."
	@docker compose down
	@tar -xzf $(BACKUP_FILE)
	@echo "✅ 復元完了"

# ===== メンテナンス =====
clean: ## 不要ファイルとコンテナを削除
	@echo "🧹 クリーンアップ中..."
	docker compose down -v
	docker system prune -f
	docker volume prune -f
	@echo "✅ クリーンアップ完了"

clean-data: ## データディレクトリをクリーンアップ
	@read -p "⚠️  すべてのデータが削除されます。続行しますか？ (y/N): " confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		rm -rf data/uploads/* data/outputs/* data/logs/*; \
		echo "✅ データをクリーンアップしました"; \
	else \
		echo "❌ キャンセルしました"; \
	fi

update: ## 依存関係を更新
	@echo "📦 依存関係を更新中..."
	pip list --outdated
	@read -p "依存関係を更新しますか？ (y/N): " confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		pip install --upgrade -r requirements.txt; \
		echo "✅ 依存関係を更新しました"; \
	fi

# ===== SSL/TLS設定 =====
generate-ssl: ## 自己署名証明書を生成（開発用）
	@echo "🔐 自己署名証明書を生成中..."
	@mkdir -p nginx/ssl
	openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
		-keyout nginx/ssl/key.pem \
		-out nginx/ssl/cert.pem \
		-subj "/C=JP/ST=Tokyo/L=Tokyo/O=LocalDev/CN=localhost"
	@echo "✅ 自己署名証明書を生成しました"

# ===== 本番環境支援 =====
deploy-check: ## 本番デプロイ前チェック
	@echo "🚀 本番デプロイ前チェック..."
	@echo "🔐 セキュリティ設定の確認..."
	@if [ ! -f nginx/ssl/cert.pem ]; then echo "❌ SSL証明書がありません"; else echo "✅ SSL証明書があります"; fi
	@if [ ! -f .env ]; then echo "❌ .envファイルがありません"; else echo "✅ .envファイルがあります"; fi
	@echo "🧪 テスト実行..."
	@make test
	@echo "🔒 セキュリティチェック..."
	@make security-check
	@echo "✅ デプロイ前チェック完了"

health-check: ## ヘルスチェック
	@echo "🏥 ヘルスチェック実行中..."
	@if curl -f http://localhost:7860/health >/dev/null 2>&1; then \
		echo "✅ アプリケーションは正常に動作しています"; \
	else \
		echo "❌ アプリケーションに問題があります"; \
		exit 1; \
	fi

# ===== 開発支援 =====
shell: ## アプリケーションコンテナに接続
	docker compose exec transcriber /bin/bash

shell-nginx: ## Nginxコンテナに接続
	docker compose exec nginx /bin/sh

watch-logs: ## リアルタイムログ監視
	@echo "📊 リアルタイムログ監視開始（Ctrl+Cで終了）"
	tail -f logs/nginx/*.log data/logs/*.json | grep --line-buffered -E "(ERROR|WARN|error|warn)" --color=always

# ===== パフォーマンス =====
benchmark: ## 簡単なパフォーマンステスト
	@echo "⚡ パフォーマンステスト実行中..."
	@echo "ヘルスチェックレスポンス時間:"
	@time curl -s http://localhost:7860/health > /dev/null

load-test: ## 負荷テスト（Apache Bench使用）
	@echo "🔥 負荷テスト実行中..."
	@if command -v ab >/dev/null 2>&1; then \
		ab -n 100 -c 10 http://localhost:7860/health; \
	else \
		echo "❌ Apache Bench (ab) がインストールされていません"; \
		echo "Ubuntuの場合: sudo apt-get install apache2-utils"; \
		echo "macOSの場合: brew install httpie"; \
	fi

# ===== 情報表示 =====
info: ## システム情報を表示
	@echo "📊 Local Web Transcriber - システム情報"
	@echo "========================================"
	@echo "🐳 Docker情報:"
	@docker version --format "Version: {{.Server.Version}}"
	@echo ""
	@echo "💾 ストレージ使用量:"
	@df -h | grep -E "(Filesystem|/$$)"
	@echo ""
	@echo "🔧 設定ファイル:"
	@if [ -f .env ]; then echo "✅ .env"; else echo "❌ .env"; fi
	@if [ -f nginx/ssl/cert.pem ]; then echo "✅ SSL証明書"; else echo "❌ SSL証明書"; fi
	@echo ""
	@echo "📁 データディレクトリ:"
	@find data/ -type f | wc -l | xargs echo "ファイル数:"
	@du -sh data/ | cut -f1 | xargs echo "使用容量:"

# ===== 緊急時対応 =====
emergency-stop: ## 緊急停止
	@echo "🚨 緊急停止中..."
	docker compose kill
	docker compose down --remove-orphans
	@echo "✅ 緊急停止完了"

recovery: ## 障害復旧
	@echo "🔧 障害復旧中..."
	@make emergency-stop
	@make clean
	@make setup
	@make build
	@make run
	@echo "✅ 障害復旧完了"
