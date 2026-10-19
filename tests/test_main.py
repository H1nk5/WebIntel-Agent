"""
WebIntel-Agent v2.0 测试套件
覆盖：抓取器、分析器、API 端点、错误处理
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from backend.main import app
from backend.config import Settings
from backend.core.fetcher import _extract_content, detect_page_type, FetchResult
from backend.core.analyzer import mock_analyze, _parse_llm_response, _to_result
from backend.models.schemas import AnalyzeResult, SentimentLevel

client = TestClient(app)


# ============== 文本提取 ==============

class TestExtractContent:
    def test_extracts_title_and_body(self):
        html = "<html><head><title>测试</title></head><body><article><p>正文内容。</p></article></body></html>"
        title, text = _extract_content(html)
        assert title == "测试"
        assert "正文内容" in text

    def test_removes_noise_tags(self):
        html = "<html><head><title>T</title></head><body><script>bad()</script><p>好</p></body></html>"
        _, text = _extract_content(html)
        assert "bad()" not in text
        assert "好" in text

    def test_no_title(self):
        html = "<html><body><p>内容</p></body></html>"
        title, _ = _extract_content(html)
        assert title == ""

    def test_cleans_whitespace(self):
        html = "<html><body><p>A</p>\n\n\n\n\n<p>B</p></body></html>"
        _, text = _extract_content(html)
        assert "\n\n\n" not in text


# ============== 页面类型检测 ==============

class TestDetectPageType:
    def test_product_page(self):
        assert detect_page_type("<html>pricing buy now</html>") == "product"

    def test_news_page(self):
        assert detect_page_type("<html>breaking news today</html>") == "news"

    def test_docs_page(self):
        assert detect_page_type("<html>api reference documentation</html>") == "docs"

    def test_default_article(self):
        assert detect_page_type("<html>hello world</html>") == "article"


# ============== LLM 响应解析 ==============

class TestParseLLMResponse:
    def test_valid_json(self):
        data = _parse_llm_response('{"summary": "test"}')
        assert data["summary"] == "test"

    def test_strips_markdown(self):
        raw = '```json\n{"summary": "test"}\n```'
        data = _parse_llm_response(raw)
        assert data["summary"] == "test"

    def test_finds_json_in_text(self):
        raw = 'Here is the result: {"summary": "ok"} done.'
        data = _parse_llm_response(raw)
        assert data["summary"] == "ok"

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            _parse_llm_response("not json at all []")


# ============== 模拟分析 ==============

class TestMockAnalyze:
    def test_returns_analyze_result(self):
        result = mock_analyze("标题", "人工智能技术取得突破性进展，多家企业实现增长。")
        assert isinstance(result, AnalyzeResult)
        assert len(result.keywords) > 0
        assert result.sentiment_score > 0.5  # 积极

    def test_negative_sentiment(self):
        result = mock_analyze("标题", "行业面临严重危机，多家企业出现亏损，市场持续下滑。")
        assert result.sentiment_label == SentimentLevel.NEGATIVE
        assert result.sentiment_score < 0.5

    def test_neutral_sentiment(self):
        result = mock_analyze("标题", "今天天气不错，适合出门散步。")
        assert result.sentiment_label == SentimentLevel.NEUTRAL


# ============== API 端点 ==============

class TestHealthEndpoint:
    def test_health(self):
        res = client.get("/api/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["version"] == "2.0.0"
        assert "llm_configured" in data

    def test_cors_only_allows_configured_local_origin(self):
        allowed = client.get("/api/health", headers={"Origin": "http://localhost:8000"})
        assert allowed.headers["access-control-allow-origin"] == "http://localhost:8000"
        denied = client.get("/api/health", headers={"Origin": "https://example.test"})
        assert "access-control-allow-origin" not in denied.headers

    def test_service_defaults_to_loopback_and_explicit_origins(self):
        local = Settings(_env_file=None)
        assert local.host == "127.0.0.1"
        assert "*" not in local.cors_origin_list


class TestAnalyzeEndpoint:
    def test_empty_url_422(self):
        res = client.post("/api/analyze", json={"url": ""})
        assert res.status_code == 422

    def test_missing_url_422(self):
        res = client.post("/api/analyze", json={})
        assert res.status_code == 422

    @patch("backend.api.routes.smart_fetch", new_callable=AsyncMock)
    def test_successful_analysis(self, mock_fetch):
        mock_fetch.return_value = FetchResult(
            url="https://example.com",
            title="测试页面",
            text="人工智能技术取得突破性进展，多家科技公司实现增长。行业前景乐观。",
            html="<html><head><title>测试页面</title></head><body><p>内容</p></body></html>",
            method="httpx",
        )
        res = client.post("/api/analyze", json={"url": "https://example.com"})
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["title"] == "测试页面"
        assert "analysis" in data
        assert "summary" in data["analysis"]
        assert "sentiment_score" in data["analysis"]
        assert "keywords" in data["analysis"]
        assert "key_insights" in data["analysis"]

    @patch("backend.api.routes.smart_fetch", new_callable=AsyncMock)
    def test_timeout_returns_502(self, mock_fetch):
        mock_fetch.side_effect = RuntimeError("抓取超时")
        res = client.post("/api/analyze", json={"url": "https://slow.com"})
        assert res.status_code == 502

    @patch("backend.api.routes.smart_fetch", new_callable=AsyncMock)
    def test_empty_content_422(self, mock_fetch):
        mock_fetch.return_value = FetchResult(
            url="https://empty.com", title="空", text="", html="", method="httpx"
        )
        res = client.post("/api/analyze", json={"url": "https://empty.com"})
        assert res.status_code == 422

    def test_auto_prepends_https(self):
        with patch("backend.api.routes.smart_fetch", new_callable=AsyncMock) as mock:
            mock.return_value = FetchResult(
                url="https://example.com", title="T",
                text="这是一段足够长的测试内容，用于验证自动补全协议的功能是否正常。",
                html="<html><body>ok</body></html>", method="httpx"
            )
            res = client.post("/api/analyze", json={"url": "example.com"})
            assert res.status_code == 200


class TestHistoryEndpoint:
    def test_history_empty(self):
        res = client.get("/api/history")
        assert res.status_code == 200
        assert "history" in res.json()

    def test_clear_history(self):
        res = client.delete("/api/history")
        assert res.status_code == 200
        assert res.json()["status"] == "cleared"


class TestIndexPage:
    def test_index(self):
        res = client.get("/")
        assert res.status_code == 200
