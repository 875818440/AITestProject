from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 应用基础
    app_name: str = "Social Media Risk Warning System"
    app_env: str = "development"
    app_debug: bool = False
    app_secret_key: str = "change-me"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # JWT
    jwt_secret_key: str = "change-me-jwt"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60

    # PostgreSQL
    database_url: str = "postgresql+asyncpg://postgres:changeme@localhost:5432/risk_warning"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Celery
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # 风险评分阈值
    risk_threshold_low: int = 31
    risk_threshold_medium: int = 61
    risk_threshold_high: int = 81
    alert_dedup_window_seconds: int = 300
    feature_sequence_length: int = 20

    # ML 模型
    model_path: str = "./ml_training/models"
    model_version: str = "v1"

    # GeoIP
    geoip_db_path: str = "./data/GeoLite2-City.mmdb"

    # 邮件
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = "noreply@yourapp.com"
    smtp_from_name: str = "安全预警系统"

    # 短信（阿里云）
    aliyun_access_key_id: str = ""
    aliyun_access_key_secret: str = ""
    aliyun_sms_sign_name: str = ""
    aliyun_sms_template_code: str = ""

    # FCM 推送
    fcm_server_key: str = ""
    fcm_api_url: str = "https://fcm.googleapis.com/fcm/send"

    # 监控
    metrics_enabled: bool = True

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def risk_level(self) -> dict:
        return {
            "normal": (0, self.risk_threshold_low - 1),
            "low": (self.risk_threshold_low, self.risk_threshold_medium - 1),
            "medium": (self.risk_threshold_medium, self.risk_threshold_high - 1),
            "high": (self.risk_threshold_high, 100),
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
