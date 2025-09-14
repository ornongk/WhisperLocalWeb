FROM python:3.11-slim

# セキュリティアップデートを含める
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# 作業ディレクトリを設定
WORKDIR /app

# 依存関係ファイルをコピー（キャッシュ効率化のため先にコピー）
COPY requirements.txt /app/requirements.txt

# Pythonパッケージをインストール
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip cache purge

# アプリケーションファイルをコピー
COPY app /app/app

# 必要なディレクトリを作成（権限問題を回避するためroot権限で作成）
RUN mkdir -p /app/app/static \
    && mkdir -p /data/uploads /data/outputs /data/logs \
    && chmod -R 755 /app /data

# 環境変数設定
ENV HOST=0.0.0.0 \
    PORT=7860 \
    MODEL_ID=base \
    DEFAULT_LANGUAGE=ja \
    DEFAULT_TASK=transcribe \
    MAX_WORKERS=2 \
    COMPUTE_TYPE=int8 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random

# ヘルスチェック追加
HEALTHCHECK --interval=30s --timeout=30s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:7860/health || exit 1

# ポート公開
EXPOSE 7860

# rootユーザーでアプリケーション起動（権限問題を回避）
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
