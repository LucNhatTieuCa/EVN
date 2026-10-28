"""Official billing portal sessions, isolated by login profile; no RF measurements."""
from .request_policy import request_json

from .paths import data_path, auth_path

import json,hashlib,threading,time,urllib.request,urllib.error
from pathlib import Path
AUTH=auth_path()
BASE='https://cskh-api.cpc.vn'
_LOCK=threading.Lock()
_SESSIONS={}

def _json(path,headers,payload=None):
    if not path.startswith('/api/'):raise ValueError('Invalid CPC path')
    req=urllib.request.Request(BASE+path,data=json.dumps(payload).encode() if payload is not None else None,headers=headers)
    return request_json(req, timeout=25)

class Client:
    def __init__(self,account):
        root=json.loads(AUTH.read_text());self.secret=root.get('accounts',{}).get(account,root)
        if self.secret.get('customer_id')!=account:raise ValueError('Billing profile mismatch')
        self.headers=None;self.login()
    def login(self,force=False):
        key=(self.secret['username'],hashlib.sha256(self.secret['password'].encode()).digest())
        with _LOCK:
            row=_SESSIONS.get(key)
            if force or not row or row['until']<time.monotonic():
                h={'Content-Type':'application/json','Accept':'application/json','Origin':'https://cskh.cpc.vn','Referer':'https://cskh.cpc.vn/'}
                payload={'username':self.secret['username'],'password':self.secret['password']}
                check=_json('/api/cskh/business-objects/check-exist-user',h,payload)
                if not check.get('isValidUser') or not check.get('isValidPassword'):raise ValueError('Billing authentication failed')
                if check.get('isShowCaptcha') or check.get('isResetPasswordTool'):raise ValueError('Billing requires interactive authentication')
                data=_json('/api/cskh/user/login',h,{**payload,'grant_type':'password','scope':'CSKH','ThongTinCaptcha':{'captcha':'undefined','token':'undefined'}})
                if not data.get('access_token'):raise ValueError('Billing login failed')
                row={'authorization':data.get('token_type','Bearer')+' '+data['access_token'],'until':time.monotonic()+min(1800,max(60,int(data.get('expires_in') or 1800)-60))};_SESSIONS[key]=row
            self.headers={'Content-Type':'application/json','Authorization':row['authorization'],'Accept':'application/json','version':'1.0'}
    def request(self,path,payload=None):
        for attempt in range(2):
            try:return _json(path,self.headers,payload)
            except urllib.error.HTTPError as error:
                if error.code!=401 or attempt:raise
                self.login(force=True)
