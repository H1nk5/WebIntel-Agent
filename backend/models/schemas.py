"""
Pydantic 严格输出 Schema
定义所有 API 请求/响应的数据结构
"""

from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum
from typing import Optional


class SentimentLevel(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class AnalyzeRequest(BaseModel):
    """分析请求"""
    url: str = Field(..., min_length=1, description="目标网页 URL")


class KeyInsight(BaseModel):
    """关键观点"""
    point: str = Field(..., description="观点内容")
    confidence: float = Field(..., ge=0.0, le=1.0, description="置信度 0-1")


class TechStackItem(BaseModel):
    """识别到的技术栈/工具"""
    name: str = Field(..., description="技术名称")
    category: str = Field(..., description="分类：框架/语言/工具/平台")


class AnalyzeResult(BaseModel):
    """LLM 分析的结构化输出"""
    summary: str = Field(..., max_length=500, description="内容摘要")
    key_insights: list[KeyInsight] = Field(
        ..., min_length=1, max_length=5, description="关键观点列表"
    )
    sentiment_score: float = Field(
        ..., ge=0.0, le=1.0,
        description="情感得分：0=极度消极, 0.5=中性, 1=极度积极"
    )
    sentiment_label: SentimentLevel = Field(..., description="情感标签")
    tech_stack: list[TechStackItem] = Field(
        default_factory=list, description="识别到的技术栈"
    )
    keywords: list[str] = Field(
        ..., min_length=1, max_length=10, description="核心关键词"
    )


class AnalyzeResponse(BaseModel):
    """API 完整响应"""
    url: str
    title: str
    page_type: str = Field(default="article", description="页面类型：article/product/news/docs")
    content_length: int = Field(..., description="原文字符数")
    analysis: AnalyzeResult
    fetched_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    status: str = "success"
    analysis_id: Optional[str] = None


class JobRequest(BaseModel):
    url: str = Field(..., min_length=1, description="目标网页 URL")


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class JobResponse(BaseModel):
    id: str
    url: str
    status: JobStatus
    result_id: Optional[str] = None
    error: Optional[str] = None
    created_at: str
    updated_at: str
    result: Optional[dict] = None


class ErrorResponse(BaseModel):
    """错误响应"""
    error: str
    detail: str
    status: str = "error"


class HealthResponse(BaseModel):
    """健康检查"""
    status: str
    service: str
    version: str
    llm_configured: bool
