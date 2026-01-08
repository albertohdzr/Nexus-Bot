import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    def __init__(self) -> None:
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_KEY")
        self.supabase_service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        self.supabase_storage_bucket = os.getenv("SUPABASE_STORAGE_BUCKET", "media")
        self.xai_api_key = os.getenv("XAI_API_KEY")
        self.xai_base_url = os.getenv("XAI_BASE_URL", "https://api.x.ai/v1")
        self.whatsapp_verify_token = os.getenv(
            "WHATSAPP_VERIFY_TOKEN", "my_secure_token"
        )
        self.whatsapp_access_token = os.getenv("WHATSAPP_ACCESS_TOKEN")
        self.cron_secret = os.getenv("CRON_SECRET")


settings = Settings()
