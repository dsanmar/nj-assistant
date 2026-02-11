import os
import sys
from pathlib import Path

from supabase import create_client

# Load .env automatically (no shell exporting needed)
try:
    from dotenv import load_dotenv
except ImportError:
    print(
        "[get_token.py] Missing dependency: python-dotenv. Install with: pip install python-dotenv",
        file=sys.stderr,
    )
    sys.exit(1)

BACKEND_DIR = Path(__file__).resolve().parents[1]  # .../backend
ENV_CANDIDATES = [
    BACKEND_DIR / ".env",
    BACKEND_DIR / ".env.local",
]

loaded_any = False
for env_path in ENV_CANDIDATES:
    if env_path.exists():
        load_dotenv(env_path, override=False)
        loaded_any = True

# Also allow environment variables already set by the shell
# (We don't require .env to exist.)
if not loaded_any:
    load_dotenv(override=False)

def must_get(name: str) -> str:
    val = os.getenv(name, "")
    if val is None:
        val = ""
    val = val.strip()
    if not val:
        print(f"[get_token.py] Missing env var: {name}", file=sys.stderr)
        sys.exit(1)
    return val

SUPABASE_URL = must_get("SUPABASE_URL")
SUPABASE_ANON_KEY = must_get("SUPABASE_ANON_KEY")
EMAIL = must_get("TEST_EMAIL")
PASSWORD = must_get("TEST_PASSWORD")

def mask_email(email: str) -> str:
    if "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        return f"{local[0]}***@{domain}"
    return f"{local[:2]}***@{domain}"

supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

try:
    res = supabase.auth.sign_in_with_password({"email": EMAIL, "password": PASSWORD})
except Exception as e:
    # Print helpful context without exposing secrets
    print("[get_token.py] Supabase sign-in failed.", file=sys.stderr)
    print(f"[get_token.py] URL: {SUPABASE_URL}", file=sys.stderr)
    print(f"[get_token.py] Email: {mask_email(EMAIL)}", file=sys.stderr)
    print(f"[get_token.py] Error: {type(e).__name__}: {e}", file=sys.stderr)
    sys.exit(1)

# supabase-py variations:
session = getattr(res, "session", None) or (res.get("session") if isinstance(res, dict) else None)
access_token = getattr(session, "access_token", None) if session else None

if not access_token:
    print(
        "[get_token.py] No access_token returned. Check: user exists, confirmed, correct project, correct password.",
        file=sys.stderr,
    )
    sys.exit(1)

print(access_token)
