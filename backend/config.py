"""
WebIntel-Agent 配置管理
使用 pydantic-settings 从环境变量 / .env 文件加载配置
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM 配置
    llm_provider: str = "deepseek"  # deepseek | openai
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"
    llm_max_tokens: int = 1500
    llm_temperature: float = 0.1

    # 抓取配置
    fetch_timeout: int = 20
    fetch_max_content_length: int = 50000

    # 服务配置
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = False
    cors_origins: str = "http://127.0.0.1:8000,http://localhost:8000"

    # 历史记录最大条数
    history_max_size: int = 100

    @property
    def cors_origin_list(self) -> list[str]:
        return list(dict.fromkeys(
            origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
        ))

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
