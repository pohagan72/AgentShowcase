# extensions.py
# Shared Flask extension instances. Lives in its own module so blueprints can
# import them without pulling in app.py (which would create a circular import).
import os
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Global limits apply to every route; per-route caps stack on top via
# @limiter.limit(...). ProxyFix in app.py ensures get_remote_address sees the
# real client IP via X-Forwarded-For from Railway / Cloudflare.
# Set RATELIMIT_STORAGE_URI=redis://... in prod when running multiple replicas.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per hour", "30 per minute"],
    storage_uri=os.environ.get("RATELIMIT_STORAGE_URI", "memory://"),
    strategy="fixed-window",
    headers_enabled=True,
)
