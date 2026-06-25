"""
网页抓取引擎
支持普通 HTTP 抓取和 Playwright 无头浏览器抓取（SPA 页面）
"""

import re
import logging
from bs4 import BeautifulSoup
import httpx

logger = logging.getLogger(__name__)


class FetchResult:
    """抓取结果"""

    def __init__(self, url: str, title: str, text: str, html: str, method: str):
        self.url = url
        self.title = title
        self.text = text
        self.html = html
        self.method = method  # "httpx" | "playwright"
        self.content_length = len(text)


async def fetch_with_httpx(url: str, timeout: int = 20) -> FetchResult:
    """使用 httpx 抓取静态页面"""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    async with httpx.AsyncClient(
        follow_redirects=True, timeout=timeout
    ) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        html = resp.text

    title, text = _extract_content(html)
    return FetchResult(url=url, title=title, text=text, html=html, method="httpx")


async def fetch_with_playwright(url: str, timeout: int = 30) -> FetchResult:
    """使用 Playwright 无头浏览器抓取 SPA 页面"""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
                )
            )
            await page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
            # 等待内容渲染
            await page.wait_for_timeout(2000)
            html = await page.content()
        finally:
            await browser.close()

    title, text = _extract_content(html)
    return FetchResult(url=url, title=title, text=text, html=html, method="playwright")


async def smart_fetch(url: str, timeout: int = 20) -> FetchResult:
    """
    智能抓取：先尝试 httpx，若内容过少则回退到 Playwright
    """
    # 第一步：httpx 快速抓取
    try:
        result = await fetch_with_httpx(url, timeout=timeout)
        if result.content_length > 100:
            logger.info(f"[httpx] 成功抓取 {url}，内容长度: {result.content_length}")
            return result
        logger.info(f"[httpx] 内容过少 ({result.content_length} chars)，回退到 Playwright")
    except Exception as e:
        logger.info(f"[httpx] 抓取失败: {e}，回退到 Playwright")

    # 第二步：Playwright 抓取 SPA
    try:
        result = await fetch_with_playwright(url, timeout=timeout + 10)
        logger.info(f"[playwright] 成功抓取 {url}，内容长度: {result.content_length}")
        return result
    except Exception as e:
        raise RuntimeError(f"两种抓取方式均失败。httpx 首先失败，playwright 错误: {e}")


def _extract_content(html: str) -> tuple[str, str]:
    """从 HTML 提取标题和正文"""
    soup = BeautifulSoup(html, "lxml")

    # 移除干扰标签
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "iframe"]):
        tag.decompose()

    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    # 优先级：article > main > body
    main = soup.find("article") or soup.find("main") or soup.find("body")
    if main:
        text = main.get_text(separator="\n", strip=True)
    else:
        text = soup.get_text(separator="\n", strip=True)

    # 清洗
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = text.strip()

    return title, text


def detect_page_type(html: str) -> str:
    """简单判断页面类型"""
    lower = html.lower()
    if any(k in lower for k in ["product", "pricing", "buy now", "add to cart", "购买", "价格"]):
        return "product"
    if any(k in lower for k in ["news", "breaking", "报道", "新闻"]):
        return "news"
    if any(k in lower for k in ["docs", "documentation", "api reference", "文档"]):
        return "docs"
    return "article"
