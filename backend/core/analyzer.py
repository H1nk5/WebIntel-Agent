"""
LLM 分析引擎
调用 DeepSeek/OpenAI API 对抓取内容进行结构化情报提取
"""

import json
import logging
from openai import AsyncOpenAI
from backend.config import settings
from backend.models.schemas import (
    AnalyzeResult, KeyInsight, TechStackItem, SentimentLevel,
)

logger = logging.getLogger(__name__)

# 系统提示词：确保 JSON 输出稳定性
SYSTEM_PROMPT = """你是一个专业的情报分析引擎。你的任务是对给定的网页内容进行结构化分析。

你必须严格返回以下 JSON 格式，不要包含任何其他文字或 markdown 标记：

{
  "summary": "一段简洁的内容摘要，不超过200字",
  "key_insights": [
    {"point": "关键观点1", "confidence": 0.9},
    {"point": "关键观点2", "confidence": 0.8},
    {"point": "关键观点3", "confidence": 0.7}
  ],
  "sentiment_score": 0.65,
  "sentiment_label": "neutral",
  "tech_stack": [
    {"name": "技术名称", "category": "框架"}
  ],
  "keywords": ["关键词1", "关键词2", "关键词3"]
}

规则：
1. summary：精炼概括全文核心内容，中文输出
2. key_insights：提取 1-3 个最重要的观点，每个附带置信度（0-1）
3. sentiment_score：0=极度消极，0.5=中性，1=极度积极
4. sentiment_label：根据 score 判断，<0.4 为 negative，>0.6 为 positive，其余为 neutral
5. tech_stack：识别文中提到的技术/工具/平台（如 React, AWS, GPT-4 等），可为空数组
6. keywords：3-8 个核心关键词
7. 所有文本内容使用中文"""


def _build_user_prompt(title: str, text: str, url: str) -> str:
    """构建用户提示词"""
    # 截断过长内容
    max_len = settings.fetch_max_content_length
    if len(text) > max_len:
        text = text[:max_len] + "\n...[内容已截断]"

    return f"""请分析以下网页内容：

来源: {url}
标题: {title}

正文:
{text}"""


def _parse_llm_response(raw: str) -> dict:
    """解析 LLM 返回的 JSON，处理常见的格式问题"""
    # 移除可能的 markdown 代码块标记
    cleaned = raw.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.warning(f"JSON 解析失败，尝试修复: {e}")
        # 尝试找到第一个 { 和最后一个 }
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1:
            return json.loads(cleaned[start : end + 1])
        raise ValueError(f"无法解析 LLM 响应为 JSON: {raw[:200]}")


def _to_result(data: dict) -> AnalyzeResult:
    """将解析后的 dict 转换为 Pydantic 模型"""
    insights = []
    for item in data.get("key_insights", []):
        insights.append(KeyInsight(
            point=item["point"],
            confidence=float(item.get("confidence", 0.5)),
        ))

    tech = []
    for item in data.get("tech_stack", []):
        tech.append(TechStackItem(
            name=item["name"],
            category=item.get("category", "其他"),
        ))

    score = float(data.get("sentiment_score", 0.5))
    label_raw = data.get("sentiment_label", "neutral")
    try:
        label = SentimentLevel(label_raw)
    except ValueError:
        label = SentimentLevel.NEUTRAL

    return AnalyzeResult(
        summary=data.get("summary", ""),
        key_insights=insights,
        sentiment_score=score,
        sentiment_label=label,
        tech_stack=tech,
        keywords=data.get("keywords", []),
    )


async def analyze_content(title: str, text: str, url: str) -> AnalyzeResult:
    """
    调用 LLM API 分析内容，返回结构化结果
    """
    client = AsyncOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
    )

    user_prompt = _build_user_prompt(title, text, url)

    try:
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=settings.llm_max_tokens,
            temperature=settings.llm_temperature,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content
        logger.info(f"LLM 响应长度: {len(raw)} chars")

        data = _parse_llm_response(raw)
        return _to_result(data)

    except Exception as e:
        logger.error(f"LLM 分析失败: {e}")
        raise RuntimeError(f"LLM 分析失败: {e}")


def mock_analyze(title: str, text: str) -> AnalyzeResult:
    """
    模拟分析（无 API Key 时的降级方案）
    """
    import re

    # 关键词提取
    english = re.findall(r"[a-zA-Z]{3,}", text.lower())
    chinese = re.findall(r"[一-鿿]{2,}", text)
    ngrams = []
    for chunk in chinese:
        for n in (4, 3, 2):
            for i in range(len(chunk) - n + 1):
                ngrams.append(chunk[i : i + n])

    stopwords = {"the", "and", "for", "that", "this", "with", "from", "are", "was",
                 "的", "是", "在", "了", "和", "与", "对", "中", "为", "也", "就", "都"}
    freq: dict[str, int] = {}
    for w in english + ngrams:
        if w not in stopwords and len(w) > 1:
            freq[w] = freq.get(w, 0) + 1
    keywords = sorted(freq, key=freq.get, reverse=True)[:6]

    # 情感
    pos = {"增长", "提升", "突破", "创新", "成功", "优秀", "领先", "利好", "繁荣"}
    neg = {"下降", "亏损", "失败", "风险", "危机", "下滑", "困难", "挑战", "利空", "萎缩"}
    pc = sum(1 for w in pos if w in text)
    nc = sum(1 for w in neg if w in text)
    if pc > nc:
        score, label = 0.75, SentimentLevel.POSITIVE
    elif nc > pc:
        score, label = 0.25, SentimentLevel.NEGATIVE
    else:
        score, label = 0.5, SentimentLevel.NEUTRAL

    summary = text[:200] + "..." if len(text) > 200 else text

    return AnalyzeResult(
        summary=summary,
        key_insights=[
            KeyInsight(point=f"文章讨论了 {keywords[0] if keywords else '某主题'} 相关内容", confidence=0.7),
        ],
        sentiment_score=score,
        sentiment_label=label,
        tech_stack=[],
        keywords=keywords,
    )
