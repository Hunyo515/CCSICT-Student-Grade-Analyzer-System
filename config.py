import os


class Config:
    """Application configuration, sourced from environment variables."""

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")

    # --- Oracle DB connection -------------------------------------------------
    ORACLE_HOST = os.getenv("ORACLE_HOST", "localhost")
    ORACLE_PORT = os.getenv("ORACLE_PORT", "1521")
    ORACLE_SERVICE = os.getenv("ORACLE_SERVICE", "XEPDB1")
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
