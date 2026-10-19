"""
API 路由定义
"""

import logging
from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, HTTPException
from backend.models.schemas import (
    AnalyzeRequest, AnalyzeResponse, ErrorResponse, HealthResponse,
    AnalyzeResult, JobRequest, JobResponse,
)
from backend.core.fetcher import smart_fetch, detect_page_type
from backend.core.analyzer import analyze_content, mock_analyze
from backend.config import settings
from backend.store import IntelStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

store = IntelStore(settings.database_path, settings.history_max_size)


def normalize_url(raw_url):
    url = raw_url.strip()
    if not url:
        raise HTTPException(status_code=422, detail="URL 不能为空")
    return url if url.startswith(("http://", "https://")) else "https://" + url


@router.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="ok",
        service="WebIntel-Agent",
        version="2.0.0",
        llm_configured=bool(settings.llm_api_key),
    )


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    responses={400: {"model": ErrorResponse}, 502: {"model": ErrorResponse}, 504: {"model": ErrorResponse}},
)
async def analyze_url(request: AnalyzeRequest):
    """分析指定 URL 的网页内容"""
    return await run_analysis(normalize_url(request.url))


async def run_analysis(url):

    # 1. 抓取网页
    try:
        fetch_result = await smart_fetch(url, timeout=settings.fetch_timeout)
    except Exception as e:
        logger.error(f"抓取失败: {e}")
        raise HTTPException(status_code=502, detail=f"抓取失败: {str(e)}")

    if fetch_result.content_length < 10:
        raise HTTPException(status_code=422, detail="网页内容过少，无法分析")

    # 2. LLM 分析
    try:
        if settings.llm_api_key:
            analysis = await analyze_content(
                fetch_result.title, fetch_result.text, fetch_result.url
            )
        else:
            logger.warning("未配置 LLM API Key，使用模拟分析")
            analysis = mock_analyze(fetch_result.title, fetch_result.text)
    except Exception as e:
        logger.error(f"分析失败，降级到模拟: {e}")
        analysis = mock_analyze(fetch_result.title, fetch_result.text)

    # 3. 检测页面类型
    page_type = detect_page_type(fetch_result.html)

    # 4. 构建响应
    response = AnalyzeResponse(
        url=fetch_result.url,
        title=fetch_result.title or "无标题",
        page_type=page_type,
        content_length=fetch_result.content_length,
        analysis=analysis,
        fetched_at=datetime.now().isoformat(),
        status="success",
    )

    # 5. 记录历史
    response.analysis_id = store.save_analysis(response)

    return response


async def process_job(job_id, url):
    store.update_job(job_id, "running")
    try:
        result = await run_analysis(url)
        store.update_job(job_id, "completed", result_id=result.analysis_id)
    except Exception as error:
        logger.exception("后台分析任务失败")
        store.update_job(job_id, "failed", error=str(error)[:500])


@router.post("/jobs", response_model=JobResponse, status_code=202)
async def create_job(request: JobRequest, background_tasks: BackgroundTasks):
    url = normalize_url(request.url)
    job = store.create_job(url)
    background_tasks.add_task(process_job, job["id"], url)
    return job


@router.get("/jobs")
async def get_jobs(limit: int = 20):
    return {"jobs": store.list_jobs(limit)}


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str):
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job


@router.get("/history")
async def get_history(limit: int = 20):
    """获取分析历史"""
    history, total = store.list_history(limit)
    return {"history": history, "total": total}


@router.get("/history/{analysis_id}", response_model=AnalyzeResponse)
async def get_history_item(analysis_id: str):
    result = store.get_analysis(analysis_id)
    if result is None:
        raise HTTPException(status_code=404, detail="分析记录不存在")
    return result


@router.delete("/history")
async def clear_history():
    """清空历史"""
    store.clear_history()
    return {"status": "cleared"}


@router.get("/settings")
async def get_settings():
    """获取当前配置（脱敏）"""
    key = settings.llm_api_key
    masked = key[:6] + "***" + key[-4:] if len(key) > 10 else ("已配置" if key else "未配置")
    return {
        "llm_provider": settings.llm_provider,
        "llm_api_key_masked": masked,
        "llm_api_key_set": bool(key),
        "llm_base_url": settings.llm_base_url,
        "llm_model": settings.llm_model,
    }


@router.post("/settings")
async def update_settings(body: dict):
    """运行时更新配置"""
    if "llm_api_key" in body:
        settings.llm_api_key = body["llm_api_key"].strip()
    if "llm_base_url" in body:
        url = body["llm_base_url"].strip()
        if url:
            settings.llm_base_url = url
    if "llm_model" in body:
        model = body["llm_model"].strip()
        if model:
            settings.llm_model = model
    if "llm_provider" in body:
        provider = body["llm_provider"].strip()
        if provider in ("deepseek", "openai"):
            settings.llm_provider = provider

    key = settings.llm_api_key
    masked = key[:6] + "***" + key[-4:] if len(key) > 10 else ("已配置" if key else "未配置")
    return {
        "status": "updated",
        "llm_api_key_masked": masked,
        "llm_api_key_set": bool(key),
        "llm_base_url": settings.llm_base_url,
        "llm_model": settings.llm_model,
        "llm_provider": settings.llm_provider,
    }
