# 配置管理
# 统一管理Agent服务的配置项，从系统环境变量读取
import os
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings
from dotenv import load_dotenv


# 项目根目录：agent-service/ 目录
PROJECT_ROOT = Path(__file__).parent.parent.resolve()

# 加载 .env 配置文件（backend/.env）
# override=False：真实系统环境变量优先级更高，.env 只补充缺失项
load_dotenv(PROJECT_ROOT / ".env", override=False)


class Settings(BaseSettings):
    # 服务监听配置
    host: str = "0.0.0.0"
    port: int = 8001

    # 阿里云千问API配置（从系统环境变量DASHSCOPE_API_KEY读取）
    dashscope_api_key: str = os.getenv("DASHSCOPE_API_KEY", "")

    # DeepSeek API配置（pydantic 显式绑定 DEEPSEEK_API_KEY，避免 field name 匹配到 DEEPSEEK_API_KEY）
    deepseek_api_key: str = Field(default="", validation_alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field(default="https://api.deepseek.com", validation_alias="DEEPSEEK_BASE_URL")
    deepseek_model: str = Field(default="deepseek-v4-flash", validation_alias="DEEPSEEK_MODEL")

    # 阿里云Embedding模型
    dashscope_embedding_model: str = "text-embedding-v2"

    # Java服务地址，用于Agent调用Java的内部API
    java_service_url: str = os.getenv("JAVA_SERVICE_URL", "http://localhost:8080")

    # ChromaDB向量库本地存储路径（绝对路径，基于项目根目录）
    chroma_db_path: str = str(PROJECT_ROOT / "chroma_db")

    # 政策文档目录（绝对路径，基于项目根目录）
    policies_data_dir: str = str(PROJECT_ROOT / "data" / "policies")

    # MySQL数据库配置
    db_host: str = os.getenv("DB_HOST", "localhost")
    db_port: int = int(os.getenv("DB_PORT", "3306"))
    db_user: str = os.getenv("DB_USER", "root")
    db_password: str = os.getenv("DB_PASSWORD", "root")
    db_name: str = os.getenv("DB_NAME", "db_ea")

    # Redis数据库配置
    redis_host: str = os.getenv("REDIS_HOST", "127.0.0.1")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    redis_password: str = os.getenv("REDIS_PASSWORD", "")
    redis_db: int = int(os.getenv("REDIS_DB", "0"))

    # Elasticsearch配置
    es_host: str = os.getenv("ES_HOST", "localhost")
    es_port: int = int(os.getenv("ES_PORT", "9200"))

    # MinIO配置
    minio_host: str = os.getenv("MINIO_HOST", "localhost:9000")
    minio_access_key: str = os.getenv("MINIO_ACCESS_KEY", "root")
    minio_secret_key: str = os.getenv("MINIO_SECRET_KEY", "88888888")
    minio_bucket_policies: str = os.getenv("MINIO_BUCKET_POLICIES", "policies")

    # Nacos 配置中心
    nacos_host: str = os.getenv("NACOS_HOST", "localhost:8848")
    nacos_data_id: str = os.getenv("NACOS_DATA_ID", "policies-gray-config")
    nacos_group: str = os.getenv("NACOS_GROUP", "DEFAULT_GROUP")

    # JWT 认证
    jwt_secret: str = os.getenv("JWT_SECRET", "employee-assistant-jwt-secret-key-2026")
    jwt_algorithm: str = "HS256"
    jwt_expire_days: int = 7

    # Agent 递归次数上限（防止 ReAct 循环无限调用工具）
    agent_recursion_limit: int = int(os.getenv("AGENT_RECURSION_LIMIT", "15"))

    # 个人数据工具链路开关（False 时只走 RAG 链路，可通过环境变量 ENABLE_PERSONAL_TOOLS 覆盖）
    enable_personal_tools: bool = Field(default=True, validation_alias="ENABLE_PERSONAL_TOOLS")


settings = Settings()
