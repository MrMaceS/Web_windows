"""
config.py
Централизованная конфигурация проекта. Все секреты и environment-зависимые
значения — только через .env, никогда не хардкодятся в коде.
"""

from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    environment: str = "development"

    database_url: str = "postgresql+psycopg2://window_user:window_pass@localhost:5432/window_landing"

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    allowed_origins: str = "http://localhost:8000,http://127.0.0.1:8000"

    @property
    def allowed_origins_list(self) -> List[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    rate_limit_lead: str = "5/minute"
    rate_limit_estimate: str = "30/minute"

    redis_url: str = ""
    telegram_max_attempts: int = 5
    telegram_retry_backoff_seconds: int = 60

    admin_session_secret: str = "dev-insecure-secret-change-me"
    admin_session_max_age_seconds: int = 8 * 60 * 60

    # --- Бизнес-настройки (плейсхолдеры — TODO: заменить на реальные данные) ---
    company_name: str = "OknoPro"                          # TODO: реальное название компании
    company_region: str = "Москва и область"                # TODO: реальный регион
    company_phone: str = "+7 (900) 000-00-00"               # TODO: реальный телефон
    company_address: str = "г. Москва, ул. Примерная, 1"     # TODO: реальный адрес
    company_work_hours: str = "Пн–Вс, 9:00–21:00"
    whatsapp_link: str = ""                                  # TODO: ссылка на WhatsApp
    telegram_link: str = ""                                  # TODO: ссылка на Telegram-канал/бота
    legal_entity_name: str = ""                              # TODO: ООО/ИП, ИНН, ОГРН — для футера
    domain: str = "https://example.com"                      # TODO: реальный домен для canonical/sitemap

    calculator_discount_percent: int = 15                    # TODO: подтвердить реальный размер скидки

    yandex_metrika_id: str = ""                              # TODO: реальный ID счётчика

    privacy_policy_url: str = "/privacy"
    consent_text: str = (
        "Согласен(на) на обработку персональных данных в соответствии "
        "с политикой конфиденциальности"
    )

    # extra="ignore": .env также содержит POSTGRES_USER/POSTGRES_PASSWORD/
    # POSTGRES_DB для подстановки переменных в docker-compose.yml — это не
    # поля приложения (оно получает готовый DATABASE_URL), но без этой
    # настройки Settings() падает при их наличии в .env.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
