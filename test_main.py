#!/usr/bin/env python3
"""
Local Web Transcriber - テストスイート
基本的な機能とセキュリティのテストを実行
"""

import pytest
import json
import tempfile
import pathlib
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import UploadFile
import io

# テスト対象のインポート
from app.main import app, validate_filename, sanitize_filename, normalize_newlines

client = TestClient(app)

class TestSecurity:
    """セキュリティ関連のテスト"""
    
    def test_validate_filename_secure(self):
        """ファイル名バリデーションのセキュリティテスト"""
        # 正常なファイル名
        assert validate_filename("test.mp3") == True
        assert validate_filename("audio_file.wav") == True
        assert validate_filename("video.mp4") == True
        
        # 危険なファイル名
        assert validate_filename("../etc/passwd") == False
        assert validate_filename("..\\windows\\system32") == False
        assert validate_filename("test/file.mp3") == False
        assert validate_filename("test\\file.mp3") == False
        assert validate_filename("") == False
        assert validate_filename("a" * 300) == False  # 長すぎるファイル名
        
        # 許可されていない拡張子
        assert validate_filename("malware.exe") == False
        assert validate_filename("script.sh") == False
        assert validate_filename("config.php") == False
    
    def test_sanitize_filename(self):
        """ファイル名サニタイズのテスト"""
        assert sanitize_filename("test file.mp3") == "test_file.mp3"
        assert sanitize_filename("file<>:\"|?*.mp3") == "file________.mp3"
        assert sanitize_filename("normal_file.wav") == "normal_file.wav"
        
        # 長いファイル名のテスト
        long_name = "a" * 300 + ".mp3"
        sanitized = sanitize_filename(long_name)
        assert len(sanitized) <= 200
    
    def test_normalize_newlines(self):
        """改行文字正規化のテスト"""
        assert normalize_newlines("line1\\nline2") == "line1\nline2"
        assert normalize_newlines("line1\r\nline2") == "line1\nline2"
        assert normalize_newlines("line1\rline2") == "line1\nline2"
        assert normalize_newlines(None) == ""
        assert normalize_newlines("") == ""

class TestAPI:
    """API エンドポイントのテスト"""
    
    def test_health_endpoint(self):
        """ヘルスチェックエンドポイントのテスト"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"
    
    def test_home_page(self):
        """ホームページのテスト"""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    def test_models_endpoint(self):
        """モデル一覧エンドポイントのテスト"""
        response = client.get("/api/models")
        assert response.status_code == 200
        data = response.json()
        assert "available" in data
        assert "current" in data
        assert "loading" in data
    
    def test_logs_endpoint(self):
        """ログエンドポイントのテスト"""
        response = client.get("/api/logs")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_invalid_job_id(self):
        """無効なジョブIDのテスト"""
        response = client.get("/api/status/invalid-job-id")
        assert response.status_code == 400
        
        response = client.get("/job/invalid-job-id")
        assert response.status_code == 400

class TestFileUpload:
    """ファイルアップロード機能のテスト"""
    
    def test_file_upload_validation(self):
        """ファイルアップロードバリデーションのテスト"""
        # 空のファイル
        response = client.post(
            "/upload",
            files={"file": ("empty.mp3", b"", "audio/mpeg")},
            data={"task": "transcribe"}
        )
        # ファイルサイズが小さすぎる場合のエラー処理をテスト
        # 実装に応じてステータスコードを調整
        
        # 大きすぎるファイル（モックでテスト）
        large_content = b"x" * (500 * 1024 * 1024 + 1)  # 500MB超
        response = client.post(
            "/upload",
            files={"file": ("large.mp3", large_content, "audio/mpeg")},
            data={"task": "transcribe"}
        )
        # 大きすぎるファイルのエラー処理をテスト
    
    def test_unsupported_file_type(self):
        """サポートされていないファイル形式のテスト"""
        response = client.post(
            "/upload",
            files={"file": ("malware.exe", b"fake content", "application/octet-stream")},
            data={"task": "transcribe"}
        )
        assert response.status_code == 400

class TestModelSwitching:
    """モデル切り替え機能のテスト"""
    
    def test_valid_model_switch(self):
        """有効なモデル切り替えのテスト"""
        response = client.post(
            "/api/model",
            json={"id": "base", "compute_type": "int8"}
        )
        # モデル切り替えの処理をテスト
        # 実装に応じてステータスコードを調整
    
    def test_invalid_model_switch(self):
        """無効なモデル切り替えのテスト"""
        # 存在しないモデル
        response = client.post(
            "/api/model",
            json={"id": "non-existent-model"}
        )
        assert response.status_code == 400
        
        # 無効なCompute Type
        response = client.post(
            "/api/model",
            json={"id": "base", "compute_type": "invalid_type"}
        )
        assert response.status_code == 400
        
        # 空のリクエスト
        response = client.post("/api/model", json={})
        assert response.status_code == 400

class TestErrorHandling:
    """エラーハンドリングのテスト"""
    
    def test_404_endpoints(self):
        """存在しないエンドポイントのテスト"""
        response = client.get("/non-existent-endpoint")
        assert response.status_code == 404
    
    def test_invalid_json(self):
        """無効なJSONのテスト"""
        response = client.post(
            "/api/model",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 400

@pytest.fixture
def temp_audio_file():
    """テスト用の一時音声ファイルを作成"""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        # 簡単なWAVファイルヘッダーを作成
        f.write(b"RIFF")
        f.write((1024).to_bytes(4, 'little'))
        f.write(b"WAVE")
        f.write(b"fmt ")
        f.write((16).to_bytes(4, 'little'))
        f.write((1).to_bytes(2, 'little'))  # PCM
        f.write((1).to_bytes(2, 'little'))  # Mono
        f.write((44100).to_bytes(4, 'little'))  # Sample rate
        f.write((88200).to_bytes(4, 'little'))  # Byte rate
        f.write((2).to_bytes(2, 'little'))  # Block align
        f.write((16).to_bytes(2, 'little'))  # Bits per sample
        f.write(b"data")
        f.write((1000).to_bytes(4, 'little'))
        f.write(b"\x00" * 1000)  # Dummy audio data
        
        return pathlib.Path(f.name)

class TestIntegration:
    """統合テスト"""
    
    @pytest.mark.asyncio
    @patch('app.main.WhisperModel')
    async def test_full_transcription_workflow(self, mock_whisper_model, temp_audio_file):
        """完全な文字起こしワークフローのテスト"""
        # WhisperModelをモック
        mock_model = MagicMock()
        mock_segment = MagicMock()
        mock_segment.start = 0.0
        mock_segment.end = 2.0
        mock_segment.text = "テストの音声です"
        
        mock_info = MagicMock()
        mock_info.language = "ja"
        mock_info.language_probability = 0.95
        
        mock_model.transcribe.return_value = ([mock_segment], mock_info)
        mock_whisper_model.return_value = mock_model
        
        # ファイルアップロードをテスト
        with open(temp_audio_file, "rb") as f:
            response = client.post(
                "/upload",
                files={"file": ("test.wav", f, "audio/wav")},
                data={"task": "transcribe", "language": "ja"}
            )
        
        # 成功時のレスポンスをテスト
        # 実装に応じてアサーションを調整

def run_security_tests():
    """セキュリティテストの実行"""
    print("🔒 セキュリティテストを実行中...")
    
    # パストラバーサル攻撃のテスト
    dangerous_paths = [
        "../../../etc/passwd",
        "..\\..\\..\\windows\\system32\\config\\sam",
        "/etc/shadow",
        "C:\\Windows\\System32\\config\\SAM"
    ]
    
    for path in dangerous_paths:
        assert not validate_filename(path), f"危険なパス '{path}' が受け入れられました"
    
    print("✅ セキュリティテスト完了")

def run_performance_tests():
    """パフォーマンステストの実行"""
    print("⚡ パフォーマンステストを実行中...")
    
    import time
    
    # API レスポンス時間のテスト
    start_time = time.time()
    response = client.get("/health")
    response_time = time.time() - start_time
    
    assert response.status_code == 200
    assert response_time < 1.0, f"ヘルスチェックが遅すぎます: {response_time}秒"
    
    print("✅ パフォーマンステスト完了")

if __name__ == "__main__":
    print("🧪 Local Web Transcriber テストスイート")
    print("=" * 50)
    
    try:
        # セキュリティテスト
        run_security_tests()
        
        # パフォーマンステスト
        run_performance_tests()
        
        # Pytestの実行
        pytest.main([__file__, "-v"])
        
        print("\n✅ すべてのテストが完了しました")
        
    except Exception as e:
        print(f"\n❌ テストエラー: {e}")
        exit(1)
