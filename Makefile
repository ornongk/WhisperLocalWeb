# 修正版 Makefile - Local Web Transcriber

.PHONY: help setup build run stop clean test logs status health-check

# デフォルトターゲット
help: ## ヘルプを表示
	@echo "Local Web Transcriber - 修正版操作コマンド"
	@echo "============================================"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ===== 環境設定 =====
setup: ## 初期環境セットアップ
	@echo "🚀 初期環境をセットアップ中..."
	@if [ ! -f .env ]; then \
		echo "MODEL_ID=base" > .env; \
		echo "DEFAULT_LANGUAGE=ja" >> .env; \
		echo "DEFAULT_TASK=transcribe" >> .env; \
		echo "MAX_WORKERS=2" >> .env; \
		echo "COMPUTE_TYPE=int8" >> .env; \
		echo "✅ .envファイルを作成しました"; \
	fi
	@mkdir -p data/uploads data/outputs data/logs logs/nginx
	@chmod 755 data logs 2>/dev/null || true
	@echo "✅ ディレクトリ構造を作成しました"

# ===== Docker操作 =====
build: ## Dockerイメージをビルド
	@echo "🔨 Dockerイメージをビルド中..."
	@if command -v docker >/dev/null 2>&1; then \
		docker compose build --no-cache; \
	else \
		echo "❌ Dockerがインストールされていません"; \
		exit 1; \
	fi

run: ## アプリケーションを起動
	@echo "🚀 アプリケーションを起動中..."
	@if ! groups | grep -q docker && [ "$$EUID" -ne 0 ]; then \
		echo "⚠️  Docker権限が必要です。sudoで実行するか、ユーザーをdockerグループに追加してください"; \
		echo "   sudo usermod -aG docker $$USER"; \
		echo "   その後、ログアウト・ログインが必要です"; \
	fi
	@docker compose up -d
	@echo "✅ アプリケーションが起動しました"
	@echo "🌐 http://localhost:7860 でアクセスできます"

run-simple: ## 最小限構成で起動（問題解決用）
	@echo "🔧 最小限構成で起動中..."
	@cp docker-compose.yml docker-compose.yml.backup 2>/dev/null || true
	@echo "services:" > docker-compose.simple.yml
	@echo "  transcriber:" >> docker-compose.simple.yml
	@echo "    build: ." >> docker-compose.simple.yml
	@echo "    ports:" >> docker-compose.simple.yml
	@echo "      - \"7860:7860\"" >> docker-compose.simple.yml
	@echo "    volumes:" >> docker-compose.simple.yml
	@echo "      - ./data:/data:rw" >> docker-compose.simple.yml
	@echo "    environment:" >> docker-compose.simple.yml
	@echo "      - MODEL_ID=base" >> docker-compose.simple.yml
	@echo "      - DEFAULT_LANGUAGE=ja" >> docker-compose.simple.yml
	@docker compose -f docker-compose.simple.yml up -d
	@echo "✅ 最小限構成で起動しました"

stop: ## アプリケーションを停止
	@echo "🛑 アプリケーションを停止中..."
	@docker compose down 2>/dev/null || docker compose -f docker-compose.simple.yml down 2>/dev/null || true
	@echo "✅ アプリケーションを停止しました"

restart: stop run ## アプリケーションを再起動

# ===== ログ・監視 =====
logs: ## ログを表示
	@docker compose logs -f 2>/dev/null || docker compose -f docker-compose.simple.yml logs -f 2>/dev/null || echo "❌ コンテナが起動していません"

logs-app: ## アプリケーションログのみ表示
	@docker compose logs -f transcriber 2>/dev/null || docker logs -f local-web-transcriber 2>/dev/null || echo "❌ アプリケーションコンテナが起動していません"

status: ## コンテナ状態を確認
	@echo "📊 コンテナ状態:"
	@docker compose ps 2>/dev/null || docker ps --filter "name=transcriber" || echo "❌ コンテナが見つかりません"
	@echo ""
	@if [ -d data ]; then \
		echo "💾 データディスク使用量:"; \
		du -sh data/ 2>/dev/null || echo "データディレクトリがありません"; \
	fi

health-check: ## ヘルスチェック
	@echo "🏥 ヘルスチェック実行中..."
	@if curl -f -s http://localhost:7860/health >/dev/null 2>&1; then \
		echo "✅ アプリケーションは正常に動作しています"; \
		curl -s http://localhost:7860/health | head -5; \
	else \
		echo "❌ アプリケーションに問題があります"; \
		echo "   ログを確認してください: make logs"; \
		exit 1; \
	fi

# ===== トラブルシューティング =====
fix-permissions: ## Docker権限問題を修正
	@echo "🔧 Docker権限を修正中..."
	@if [ "$$EUID" -eq 0 ]; then \
		echo "rootユーザーで実行されています"; \
	else \
		echo "現在のユーザーをdockerグループに追加します..."; \
		sudo usermod -aG docker $$USER; \
		echo "✅ ユーザーをdockerグループに追加しました"; \
		echo "⚠️  ログアウト・ログインしてから再実行してください"; \
	fi

check-docker: ## Docker環境をチェック
	@echo "🔍 Docker環境をチェック中..."
	@if command -v docker >/dev/null 2>&1; then \
		echo "✅ Docker: $$(docker --version)"; \
	else \
		echo "❌ Dockerがインストールされていません"; \
	fi
	@if command -v docker-compose >/dev/null 2>&1 || docker compose version >/dev/null 2>&1; then \
		echo "✅ Docker Compose: 利用可能"; \
	else \
		echo "❌ Docker Composeがインストールされていません"; \
	fi
	@if docker info >/dev/null 2>&1; then \
		echo "✅ Docker daemon: 実行中"; \
	else \
		echo "❌ Docker daemonに接続できません（権限問題の可能性）"; \
	fi

clean: ## 不要ファイルとコンテナを削除
	@echo "🧹 クリーンアップ中..."
	@docker compose down -v 2>/dev/null || docker compose -f docker-compose.simple.yml down -v 2>/dev/null || true
	@docker system prune -f 2>/dev/null || true
	@echo "✅ クリーンアップ完了"

clean-data: ## データディレクトリをクリーンアップ
	@read -p "⚠️  すべてのデータが削除されます。続行しますか？ (y/N): " confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		rm -rf data/uploads/* data/outputs/* data/logs/* 2>/dev/null || true; \
		echo "✅ データをクリーンアップしました"; \
	else \
		echo "❌ キャンセルしました"; \
	fi

# ===== 緊急時対応 =====
emergency-stop: ## 緊急停止
	@echo "🚨 緊急停止中..."
	@docker kill $$(docker ps -q --filter "name=transcriber") 2>/dev/null || true
	@docker compose down --remove-orphans 2>/dev/null || true
	@docker compose -f docker-compose.simple.yml down --remove-orphans 2>/dev/null || true
	@echo "✅ 緊急停止完了"

reset: ## 完全リセット
	@echo "🔄 システムをリセット中..."
	@make emergency-stop
	@make clean
	@make setup
	@echo "✅ リセット完了。make build && make run でアプリケーションを起動してください"

# ===== 開発支援 =====
shell: ## アプリケーションコンテナに接続
	@docker compose exec transcriber /bin/bash 2>/dev/null || docker exec -it local-web-transcriber /bin/bash 2>/dev/null || echo "❌ アプリケーションコンテナが起動していません"

# ===== 情報表示 =====
info: ## システム情報を表示
	@echo "📊 Local Web Transcriber - システム情報"
	@echo "========================================"
	@echo "🐳 Docker情報:"
	@docker version --format "Version: {{.Server.Version}}" 2>/dev/null || echo "Dockerが利用できません"
	@echo ""
	@echo "📁 プロジェクト情報:"
	@echo "ディレクトリ: $$(pwd)"
	@if [ -d data ]; then \
		echo "データディレクトリ: 存在"; \
		find data/ -type f 2>/dev/null | wc -l | xargs echo "ファイル数:"; \
	else \
		echo "データディレクトリ: 未作成"; \
	fi
	@echo ""
	@echo "🔧 設定ファイル:"
	@if [ -f .env ]; then echo "✅ .env"; else echo "❌ .env"; fi
	@if [ -f Dockerfile ]; then echo "✅ Dockerfile"; else echo "❌ Dockerfile"; fi
	@if [ -f docker-compose.yml ]; then echo "✅ docker-compose.yml"; else echo "❌ docker-compose.yml"; fi

# テスト用（簡易版）
test: ## 簡単なテストを実行
	@echo "🧪 簡単なテストを実行中..."
	@if make health-check >/dev/null 2>&1; then \
		echo "✅ ヘルスチェック: 通過"; \
	else \
		echo "❌ ヘルスチェック: 失敗"; \
	fi
	@if [ -f app/main.py ]; then \
		echo "✅ メインアプリケーション: 存在"; \
	else \
		echo "❌ メインアプリケーション: 不明"; \
	fi
