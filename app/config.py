from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://postgres:password@localhost:5432/cofounders_matrimony"
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Future: ChatGPT API Integration
    OPENAI_API_KEY: str = ""
    
    class Config:
        env_file = ".env"

# ── Email (SMTP) ──────────────────────────────────────────────────────────────
# Leave SMTP_HOST empty to disable emails (they'll be logged instead).
SMTP_HOST:     str  = ""                          # e.g. "smtp.gmail.com"
SMTP_PORT:     int  = 587
SMTP_USER:     str  = ""                          # your Gmail / SMTP username
SMTP_PASSWORD: str  = ""                          # app password
SMTP_FROM:     str  = "noreply@cofoundersmatrimony.com"
SMTP_TLS:      bool = True
APP_URL: str = ["http://localhost:5173", "http://localhost:3000"]
settings = Settings()
