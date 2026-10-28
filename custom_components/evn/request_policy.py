"""One paced EVN request at a time across login, data and invoice clients."""
import json
import random
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

_LOCK = threading.Lock()
_next_request = 0.0
_cooldown = 0.0
INTERVAL = 2.0
MAX_RESPONSE_BYTES = 32 * 1024 * 1024

class ProviderCooldown(OSError):
    """Provider asked this client to pause; retry from a saved checkpoint later."""


def _retry_after(value):
    try:
        return max(0.0, float(value))
    except (ValueError, TypeError):
        try:
            return max(0.0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return 0.0


def request_json(request, timeout=30):
    """Retry transient failures only. Never retry invalid credentials or CAPTCHA."""
    global _next_request, _cooldown
    for attempt in range(3):
        with _LOCK:
            now = time.monotonic()
            if _cooldown > now:
                raise ProviderCooldown('EVN requests temporarily paused')
            delay = max(0.0, _next_request - now)
            if delay:
                time.sleep(delay)
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    raw = response.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise ValueError('EVN response exceeds size limit')
                return json.loads(raw)
            except urllib.error.HTTPError as error:
                if error.code not in (429, 500, 502, 503, 504):
                    raise
                if error.code == 429:
                    _cooldown = time.monotonic() + max(60.0, _retry_after(error.headers.get('Retry-After')))
                    raise ProviderCooldown('EVN rate limit; checkpoint retained') from None
                if attempt == 2:
                    _cooldown = time.monotonic() + max(60.0, _retry_after(error.headers.get('Retry-After')))
                    raise ProviderCooldown('EVN temporarily unavailable') from None
                _next_request = time.monotonic() + max(2 ** (attempt + 2), _retry_after(error.headers.get('Retry-After'))) + random.uniform(0, 1)
                if _next_request - time.monotonic() > 30:
                    _cooldown = _next_request
                    raise ProviderCooldown('EVN requested a longer pause') from None
            except (urllib.error.URLError, TimeoutError):
                if attempt == 2:
                    raise
                _next_request = time.monotonic() + 2 ** (attempt + 2) + random.uniform(0, 1)
            finally:
                _next_request = max(_next_request, time.monotonic() + INTERVAL)
    raise ProviderCooldown('EVN temporarily unavailable')
