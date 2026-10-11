"""Environment-based configuration. Every setting has a safe default for a public demo."""
import os
def _b(k, d): return os.environ.get(k, str(d)).strip().lower() in ("1", "true", "yes", "on")
PORT = int(os.environ.get("PORT", "8000"))
HOST = os.environ.get("COLSTORSO_HOST", "0.0.0.0")
DB_PATH = os.environ.get("COLSTORSO_DB")                       # SQLite file path (default ./data/colstorso.db)
PUBLIC_DEMO = _b("COLSTORSO_PUBLIC_DEMO", True)                # demo personas only, synthetic data, API docs off
RATE_LIMIT_PER_MIN = int(os.environ.get("COLSTORSO_RATE_LIMIT", "240"))        # per client IP, all requests
WRITE_LIMIT_PER_MIN = int(os.environ.get("COLSTORSO_WRITE_RATE_LIMIT", "60"))  # per IP, POST/PUT/DELETE
RESET_LIMIT_PER_HOUR = int(os.environ.get("COLSTORSO_RESET_LIMIT", "6"))       # global
MAX_UPLOAD_MB = float(os.environ.get("COLSTORSO_MAX_UPLOAD_MB", "5"))
AUTO_SEED = _b("COLSTORSO_AUTO_SEED", True)                    # build demo data on first start if the DB is empty
TRUST_PROXY = _b("COLSTORSO_TRUST_PROXY", True)                # use X-Forwarded-For from the host's proxy for rate limits
