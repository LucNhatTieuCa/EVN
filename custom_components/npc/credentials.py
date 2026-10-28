"""Admin options-flow credentials. No secrets returned to the browser or logs."""
from .request_policy import request_json

from .paths import data_path, auth_path

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import threading
import urllib.error
import urllib.request
from uuid import uuid4
from zoneinfo import ZoneInfo
from cryptography.fernet import Fernet

AUTH = auth_path()
HISTORY = data_path('private', 'history', 'credentials')
KEY = AUTH.parent / 'evn-credentials-history.key'
_LOCK = threading.Lock()

class CredentialsError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)

def current_username(account=None):
    if not AUTH.exists():
        return ''
    root=json.loads(AUTH.read_text());row=root.get('accounts',{}).get(account,root) if account else root
    return str(row.get('username') or '')

def _request(url, payload=None, token=None):
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(url, data=json.dumps(payload).encode() if payload is not None else None, headers=headers)
    try:
        result = request_json(req, timeout=25)
    except urllib.error.HTTPError as error:
        raise CredentialsError('invalid_auth' if error.code in (400, 401, 403) else 'cannot_connect') from None
    except (OSError, ValueError):
        raise CredentialsError('cannot_connect') from None
    if not isinstance(result, dict):
        raise CredentialsError('cannot_connect')
    return result

def validate(username, password, accounts):
    """Read-only login and identity check. Never fetch/write production data here."""
    login = _request('https://cskh.evn.com.vn/cskh/v1/auth/login', {
        'username': username, 'password': password,
        'deviceInfo': {'deviceId': 'ha-evn-settings', 'deviceType': 'Android/HomeAssistant'}})
    data = login.get('data') or {}
    token = data.get('accessToken')
    if not login.get('success') or not token:
        raise CredentialsError('invalid_auth')
    identity = (data.get('data') or {}).get('maKhang')
    for account in accounts:
        if identity == account:
            continue
        switched = _request('https://cskh.evn.com.vn/cskh/v1/user/swich/' + account, token=token)
        row = switched.get('data') or {}
        if not switched.get('success') or not row.get('accessToken') or (row.get('data') or {}).get('maKhang') != account:
            raise CredentialsError('account_not_linked')
    # Official billing portal login requirements are checked before replacing the shared secret.
    info = _request('https://cskh-api.cpc.vn/api/cskh/business-objects/check-exist-user', {'username': username, 'password': password})
    if not info.get('isValidUser') or not info.get('isValidPassword'):
        raise CredentialsError('invalid_auth')
    if info.get('isShowCaptcha') or info.get('isResetPasswordTool'):
        raise CredentialsError('interactive_auth')
    legacy = _request('https://cskh-api.cpc.vn/api/cskh/user/login', {
        'username': username, 'password': password, 'grant_type': 'password', 'scope': 'CSKH',
        'ThongTinCaptcha': {'captcha': 'undefined', 'token': 'undefined'}})
    if not legacy.get('access_token'):
        raise CredentialsError('invalid_auth')

def save_credentials(username, password, accounts):
    """Executor only: validate, encrypted immutable snapshot, CAS, atomic replace."""
    username = str(username or '').strip()
    if not username:
        raise CredentialsError('invalid_auth')
    with _LOCK:
        before = AUTH.read_bytes() if AUTH.exists() else None
        old = json.loads(before) if before is not None else {}
        if not password:
            profiles=[old,*list((old.get('accounts') or {}).values())]
            matched=next((row for row in profiles if row.get('username')==username and row.get('password')),None)
            if not matched:raise CredentialsError('password_required')
            password=matched['password']
        accounts = sorted(set(accounts))
        if not accounts or any(not str(account).isalnum() or not str(account).startswith('PC') for account in accounts):
            raise CredentialsError('account_not_linked')
        validate(username, password, accounts)
        new = dict(old)
        new.update({'username': username, 'password': password})
        new.setdefault('customer_id', accounts[0])
        new['accounts'] = dict(old.get('accounts') or {})
        if old.get('customer_id') and old.get('username') and old.get('password'):
            new['accounts'].setdefault(old['customer_id'],{key:old[key] for key in ['customer_id','username','password']})
        for account in accounts:
            row = dict(new['accounts'].get(account) or {})
            row.update({'username': username, 'password': password, 'customer_id': account})
            new['accounts'][account] = row
        after = json.dumps(new, ensure_ascii=False, indent=2).encode()
        if before == after:
            return False
        stamp = datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%Y%m%d-%H%M%S-%f')
        dest = HISTORY / (stamp + '-' + uuid4().hex[:8])
        dest.mkdir(parents=True, exist_ok=False)
        AUTH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not KEY.exists():
            fd = os.open(KEY, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as handle:
                handle.write(Fernet.generate_key())
        cipher = Fernet(KEY.read_bytes())
        snapshot = dest / 'credentials-before.fernet'
        snapshot.write_bytes(cipher.encrypt(before if before is not None else b''))
        if cipher.decrypt(snapshot.read_bytes()) != (before if before is not None else b''):
            raise CredentialsError('save_failed')
        snapshot.chmod(0o444)
        manifest = dest / 'manifest.json'
        manifest.write_text(json.dumps({'id': 'npc-credentials-update', 'time': stamp,
            'target': 'custom-secret/evn-cpc.json', 'key_reference': str(KEY),
            'before_sha256': hashlib.sha256(before).hexdigest() if before is not None else None,
            'after_sha256': hashlib.sha256(after).hexdigest(), 'accounts': accounts,
            'new_components': ['custom-secret/evn-cpc.json'] if before is None else [],
            'deleted_components': []}, indent=2))
        manifest.chmod(0o444)
        if (AUTH.read_bytes() if AUTH.exists() else None) != before:
            raise CredentialsError('concurrent_change')
        temporary = AUTH.parent / ('.evn-auth-' + uuid4().hex)
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as handle:
                handle.write(after)
                handle.flush()
                os.fsync(handle.fileno())
            if temporary.read_bytes() != after:
                raise CredentialsError('save_failed')
            if (AUTH.read_bytes() if AUTH.exists() else None) != before:
                raise CredentialsError('concurrent_change')
            os.replace(temporary, AUTH)
            if AUTH.read_bytes() != after:
                # Preserve failed result; only rollback our own exact written version.
                raise CredentialsError('save_failed')
        finally:
            temporary.unlink(missing_ok=True)
        from .cpc_session import _SESSIONS as sessions
        from .billing_session import _SESSIONS as billing_sessions
        sessions.clear();billing_sessions.clear()
        return True


def discover_accounts(username, password):
    """Get customer choices from official authenticated CPC, not HA entries."""
    username = str(username or '').strip()
    if not username or not password:
        raise CredentialsError('password_required')
    payload = {'username': username, 'password': password}
    info = _request('https://cskh-api.cpc.vn/api/cskh/business-objects/check-exist-user', payload)
    if not info.get('isValidUser') or not info.get('isValidPassword'):
        raise CredentialsError('invalid_auth')
    if info.get('isShowCaptcha') or info.get('isResetPasswordTool'):
        raise CredentialsError('interactive_auth')
    login = _request('https://cskh-api.cpc.vn/api/cskh/user/login', {
        **payload, 'grant_type': 'password', 'scope': 'CSKH',
        'ThongTinCaptcha': {'captcha': 'undefined', 'token': 'undefined'}})
    if not login.get('access_token'):
        raise CredentialsError('invalid_auth')
    result = _request('https://cskh-api.cpc.vn/api/remote/customers/infos', token=login['access_token'])
    found = {}
    def collect(rows):
        if not isinstance(rows, list):
            return
        for row in rows:
            if not isinstance(row, dict):
                continue
            code = str(row.get('customerCode') or '').strip().upper()
            if code.startswith('PC') and code.isalnum():
                found[code] = {'customer_id': code, 'name': str(row.get('customerName') or '').strip()}
            collect(row.get('childCustomerCodes'))
    collect(result.get('customerCodes'))
    if not found:
        raise CredentialsError('no_linked_accounts')
    # Also verify the new-app login before displaying the account picker.
    new = _request('https://cskh.evn.com.vn/cskh/v1/auth/login', {
        **payload, 'deviceInfo': {'deviceId': 'ha-evn-discovery', 'deviceType': 'Android/HomeAssistant'}})
    if not new.get('success') or not (new.get('data') or {}).get('accessToken'):
        raise CredentialsError('invalid_auth')
    return [found[code] for code in sorted(found)]


def profile_accounts(account,configured):
    if not AUTH.exists():return [account]
    root=json.loads(AUTH.read_text());rows=root.get('accounts') or {};username=(rows.get(account) or root).get('username')
    return sorted({code for code in configured if (rows.get(code) or root).get('username')==username}|{account})
