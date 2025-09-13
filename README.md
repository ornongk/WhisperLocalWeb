# 🎤 Local Web Transcriber (Enhanced Version)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=flat&logo=docker&logoColor=white)](https://www.docker.com/)
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=flat&logo=fastapi)](https://fastapi.tiangolo.com/)

高性能・高セキュリティなローカル音声・動画文字起こしWebアプリケーション。OpenAI Whisperを使用し、プライバシーを重視したオフライン処理を実現します。

## ✨ **主な機能**

### 🎯 **コア機能**
- **高精度文字起こし**: OpenAI Whisper使用による多言語対応
- **動画対応**: 音声ファイルに加えて動画ファイルからの音声抽出
- **複数出力形式**: TXT, SRT, VTT, JSON形式での出力
- **リアルタイム進捗**: WebUI上でのリアルタイム処理状況表示
- **モデル切り替え**: tiny〜large-v3まで用途に応じた選択可能

### 🔒 **セキュリティ機能**
- **ファイル検証**: 拡張子・サイズ・内容の厳格な検証
- **パストラバーサル対策**: ディレクトリトラバーサル攻撃の防御
- **自動クリーンアップ**: アップロードファイルの自動削除
- **非特権実行**: rootユーザーを使わない安全な実行
- **セキュリティヘッダー**: XSS, CSRF, Clickjacking対策

### ⚡ **パフォーマンス機能**
- **非同期処理**: FastAPIによる高パフォーマンス
- **リソース制限**: メモリ・CPU使用量の制限
- **プログレス最適化**: 効率的な進捗更新
- **Nginx統合**: リバースプロキシによる高速化

### 🛠 **運用機能**
- **ヘルスチェック**: アプリケーション状態の監視
- **自動バックアップ**: データの自動保護
- **ログ集約**: 詳細なログ記録と監視
- **コンテナ監視**: Prometheus連携対応

## 🚀 **クイックスタート**

### **必要な環境**
- Docker & Docker Compose
- 4GB以上のRAM推奨
- CUDA対応GPU（オプション、CPU使用も可能）

### **1. リポジトリのクローン**
```bash
git clone https://github.com/yourusername/local-web-transcriber-improved.git
cd local-web-transcriber-improved
```

### **2. 初期設定**
```bash
# 自動セットアップ
make setup

# 環境変数を編集
nano .env
```

### **3. アプリケーション起動**
```bash
# ビルドと起動
make build
make run

# ブラウザでアクセス
open http://localhost:7860
```

## 📋 **詳細セットアップ**

### **環境変数設定**

`.env`ファイルで以下の設定が可能です：

```bash
# === 基本設定 ===
MODEL_ID=base                    # Whisperモデル (tiny/base/small/medium/large-v3)
COMPUTE_TYPE=int8                # 演算精度 (int8/float16/float32)
DEFAULT_LANGUAGE=ja              # デフォルト言語
MAX_WORKERS=2                    # 並列処理数

# === セキュリティ設定 ===
MAX_FILE_SIZE=524288000          # 最大ファイルサイズ (500MB)
FILE_RETENTION_HOURS=24          # ファイル保持時間

# === パフォーマンス設定 ===
MEMORY_LIMIT=4G                  # メモリ制限
CPU_LIMIT=2.0                    # CPU制限
```

### **SSL/HTTPS設定**

本番環境でのHTTPS対応：

```bash
# 自己署名証明書生成（開発用）
make generate-ssl

# Let's Encrypt証明書（本番用）
# certbot等を使用してnginx/ssl/に配置
```

### **監視機能の有効化**

```bash
# Prometheus監視付きで起動
make run-monitoring

# 監視ダッシュボード
open http://localhost:9090
```

## 🔧 **開発・運用コマンド**

Makefileによる豊富な運用支援コマンド：

```bash
# === 基本操作 ===
make help                # ヘルプ表示
make setup               # 初期環境セットアップ
make build               # Dockerイメージビルド
make run                 # アプリケーション起動
make stop                # アプリケーション停止
make restart             # アプリケーション再起動

# === 開発支援 ===
make test                # テスト実行
make test-coverage       # カバレッジ付きテスト
make lint                # コード品質チェック
make format              # コードフォーマット
make security-check      # セキュリティチェック

# === 監視・ログ ===
make logs                # 全ログ表示
make logs-app            # アプリログのみ
make status              # システム状態確認
make health-check        # ヘルスチェック

# === バックアップ・復旧 ===
make backup              # データバックアップ
make restore BACKUP_FILE=filename  # データ復元
make clean               # システムクリーンアップ

# === 本番運用 ===
make deploy-check        # デプロイ前チェック
make load-test           # 負荷テスト
make benchmark           # パフォーマンステスト
```

## 🛡️ **セキュリティ対策**

### **実装済み対策**
- ✅ **ファイルアップロード検証**: 拡張子・サイズ・内容チェック
- ✅ **パストラバーサル対策**: `../`等の危険なパス排除
- ✅ **リソース制限**: DoS攻撃対策
- ✅ **セキュリティヘッダー**: XSS, CSRF, Clickjacking対策
- ✅ **非特権実行**: rootユーザーを使わない安全な実行
- ✅ **自動クリーンアップ**: 機密ファイルの自動削除

### **セキュリティチェック**
```bash
# 定期的なセキュリティ監査
make security-check

# 依存関係の脆弱性チェック
safety check

# コードの静的解析
bandit -r app/
```

## 📊 **サポート形式**

### **入力形式**
| 形式 | 拡張子 | 備考 |
|------|--------|------|
| 音声 | MP3, WAV, M4A, FLAC, OGG | 高品質音声推奨 |
| 動画 | MP4, AVI, MOV, WebM | 音声が自動抽出 |

### **出力形式**
| 形式 | 用途 | 特徴 |
|------|------|------|
| TXT | テキスト編集 | プレーンテキスト |
| SRT | 字幕ファイル | 動画編集ソフト対応 |
| VTT | Web字幕 | ブラウザ再生対応 |
| JSON | API連携 | 詳細なメタデータ付き |

## ⚙️ **システム要件**

### **推奨環境**

| コンポーネント | 推奨スペック | 備考 |
|----------------|--------------|------|
| CPU | 4コア以上 | AVX2対応推奨 |
| RAM | 8GB以上 | large-v3使用時は16GB推奨 |
| ストレージ | 10GB以上 | モデル・データ用 |
| GPU | CUDA対応（オプション） | 高速処理用 |

### **モデル別要件**

| モデル | RAM使用量 | 処理速度 | 精度 |
|--------|-----------|----------|------|
| tiny | ~1GB | 高速 | 基本 |
| base | ~2GB | 高速 | 良好 |
| small | ~3GB | 中程度 | 良好 |
| medium | ~5GB | 中程度 | 高精度 |
| large-v3 | ~10GB | 低速 | 最高精度 |

## 🔍 **トラブルシューティング**

### **よくある問題**

#### **1. メモリ不足エラー**
```bash
# モデルサイズを小さく
MODEL_ID=base
COMPUTE_TYPE=int8

# メモリ制限を調整
MEMORY_LIMIT=2G
```

#### **2. ファイルアップロード失敗**
```bash
# ファイルサイズを確認
ls -lh your_file.mp4

# 制限値を調整
MAX_FILE_SIZE=1073741824  # 1GB
```

#### **3. SSL証明書エラー**
```bash
# 自己署名証明書を再生成
make generate-ssl

# 権限を確認
chmod 600 nginx/ssl/*.pem
```

### **ログ確認**
```bash
# アプリケーションログ
make logs-app

# エラーログのみ
docker compose logs transcriber | grep ERROR

# Nginxエラーログ
cat logs/nginx/transcriber_error.log
```

### **リセット・復旧**
```bash
# 完全リセット
make emergency-stop
make clean
make setup
make build
make run

# データのみクリーンアップ
make clean-data
```

## 📈 **パフォーマンス最適化**

### **GPU使用時**
```bash
# CUDA対応の確認
docker run --gpus all nvidia/cuda:11.8-runtime-ubuntu20.04 nvidia-smi

# GPU使用でのモデル設定
MODEL_ID=large-v3
COMPUTE_TYPE=float16
```

### **CPU最適化**
```bash
# ワーカー数の調整
MAX_WORKERS=4  # CPUコア数に応じて調整

# メモリ効率重視
COMPUTE_TYPE=int8
MODEL_ID=base
```

### **ネットワーク最適化**
```bash
# Nginxでの静的ファイルキャッシュ
# nginx/default.confで設定済み

# 圧縮の有効化
gzip on;
gzip_types text/plain application/json;
```

## 🤝 **コントリビューション**

プロジェクトへの貢献を歓迎します！

### **開発環境セットアップ**
```bash
# 開発用依存関係のインストール
make install-dev

# 開発モードで起動
make run-dev

# テスト実行
make test

# コード品質チェック
make lint
make format
```

### **プルリクエストガイドライン**
1. フォークしてブランチを作成
2. 変更内容をテスト
3. コード品質チェック通過
4. わかりやすいコミットメッセージ
5. プルリクエスト作成

## 📄 **ライセンス**

MIT License - 詳細は[LICENSE](LICENSE)ファイルを参照

## 🙏 **謝辞**

- [OpenAI Whisper](https://github.com/openai/whisper) - 音声認識エンジン
- [faster-whisper](https://github.com/guillaumekln/faster-whisper) - 高速化実装
- [FastAPI](https://fastapi.tiangolo.com/) - Webフレームワーク
- [Docker](https://www.docker.com/) - コンテナ化

## 📞 **サポート**

- **Issues**: GitHub Issuesで問題を報告
- **Discussions**: GitHub Discussionsで質問・提案
- **Wiki**: プロジェクトWikiで詳細ドキュメント

---

**🚀 Enjoy transcribing with privacy and performance! 🎯**
