from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://founder_user:founder123@localhost:5432/cofounders_db"
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    OPENAI_API_KEY: str = ""

    SMTP_HOST:     str  = "smtp.gmail.com"
    SMTP_PORT:     int  = 587
    SMTP_USER:     str  = "hasarsahar@gmail.com"
    SMTP_PASSWORD: str  = "pfdg leaa mkhb gjzo"  # use your real 16-char app password
    SMTP_FROM:     str  = "hasarsahar@gmail.com"
    SMTP_TLS:      bool = True
    APP_URL:       str  = "http://localhost:3000"

    class Config:          # ← indented INSIDE Settings
        env_file = ".env"

settings = Settings()