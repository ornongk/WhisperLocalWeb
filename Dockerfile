FROM python:3.11-slim

# セキュリティアップデートを含める
RUN apt-get update && apt-get install -y --no-install-recommends \
    # 必須パッケージのみインストール
    ffmpeg \
    git \
    # セキュリティ関連の追加
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# 非特権ユーザーを作成
RUN groupadd -r appgroup && useradd -r -g appgroup -u 1000 appuser

# 作業ディレクトリを設定
WORKDIR /app

# 依存関係ファイルをコピー（キャッシュ効率化のため先にコピー）
COPY requirements.txt /app/requirements.txt

# Pythonパッケージをインストール
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    # セキュリティ：不要なキャッシュを削除
    && pip cache purge

# アプリケーションファイルをコピー
COPY app /app/app

# 必要なディレクトリを作成し、適切な権限を設定
RUN mkdir -p /app/app/static \
    && mkdir -p /data/uploads /data/outputs /data/logs \
    && chown -R appuser:appgroup /app /data \
    && chmod -R 755 /app /data

# 非特権ユーザーに切り替え
USER appuser

# 環境変数設定
ENV HOST=0.0.0.0 \
    PORT=7860 \
    MODEL_ID=base \
    DEFAULT_LANGUAGE=ja \
    DEFAULT_TASK=transcribe \
    MAX_WORKERS=2 \
    COMPUTE_TYPE=int8 \
    # Pythonの出力バッファリングを無効化（ログ表示の改善）
    PYTHONUNBUFFERED=1 \
    # セキュリティ：パスハッシュランダム化を有効化
    PYTHONHASHSEED=random

# ヘルスチェック追加
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:7860/health')" || exit 1

# ポート公開
EXPOSE 7860

# アプリケーション起動
# セキュリティ：プロセス制限とワーカー数制限
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1", "--access-log"]
