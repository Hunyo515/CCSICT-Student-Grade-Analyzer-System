import os
<<<<<<< HEAD
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()
=======
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423


class Config:
    """Application configuration, sourced from environment variables."""

<<<<<<< HEAD
    SECRET_KEY = os.getenv("SECRET_KEY", "")
=======
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423

    # --- Oracle DB connection -------------------------------------------------
    ORACLE_HOST = os.getenv("ORACLE_HOST", "localhost")
    ORACLE_PORT = os.getenv("ORACLE_PORT", "1521")
    ORACLE_SERVICE = os.getenv("ORACLE_SERVICE", "XEPDB1")
<<<<<<< HEAD
    ORACLE_SCHEMA = os.getenv("ORACLE_SCHEMA", "")
=======
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423
    ORACLE_USER = os.getenv("ORACLE_USER", "student")
    ORACLE_PASSWORD = os.getenv("ORACLE_PASSWORD", "1j2u3n4e")

    ORACLE_DSN = f"{ORACLE_HOST}:{ORACLE_PORT}/{ORACLE_SERVICE}"

    # Connection pool sizing
    ORACLE_POOL_MIN = int(os.getenv("ORACLE_POOL_MIN", "2"))
    ORACLE_POOL_MAX = int(os.getenv("ORACLE_POOL_MAX", "10"))
    ORACLE_POOL_INCREMENT = int(os.getenv("ORACLE_POOL_INCREMENT", "1"))

    # --- Pagination defaults ---------------------------------------------------
    DEFAULT_PAGE_SIZE = 10

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
<<<<<<< HEAD

    SESSION_COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").lower() == "true"
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024
    AUTH_IP_LIMIT = int(os.getenv("AUTH_IP_LIMIT", "1200"))
    AUTH_IP_WINDOW = int(os.getenv("AUTH_IP_WINDOW", "900"))
    SECURITY_DB = os.getenv("SECURITY_DB", "")
    MAIL_HOST = os.getenv('MAIL_HOST', '')
    MAIL_PORT = int(os.getenv('MAIL_PORT', '587'))
    MAIL_FROM = os.getenv('MAIL_FROM', '')
    MAIL_USERNAME = os.getenv('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD', '')
    MAIL_SSL = os.getenv('MAIL_SSL', 'false').lower() == 'true'
=======
>>>>>>> cbc75e39d66c03cb8a824f033eed3def1d11e423
