"""Private runtime paths resolved from Home Assistant's configuration directory."""

from pathlib import Path
ROOT = Path('/config')
_AUTH = None

def configure(hass):
    global ROOT, _AUTH
    ROOT = Path(hass.config.path())
    legacy = ROOT / '.codex-secrets' / 'evn-cpc.json'
    if _AUTH is None:
        _AUTH = legacy if legacy.exists() else data_path('private', 'credentials.json')

def data_path(*parts):
    return ROOT.joinpath('evnvn', *parts)

def auth_path():
    return _AUTH or data_path('private', 'credentials.json')
