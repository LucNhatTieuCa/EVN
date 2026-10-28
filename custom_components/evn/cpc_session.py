"""Official new-app session reuse. Credentials/tokens never leave memory or protected file."""
from .request_policy import request_json

from .paths import data_path, auth_path

import hashlib,json,threading,time,urllib.request,urllib.error
from pathlib import Path
AUTH=auth_path()
_LOCK=threading.Lock()
_SESSIONS={}

def _json(url,payload=None,token=None):
    if not url.startswith(('https://cskh.evn.com.vn/','https://cskh-api.cpc.vn/')):raise ValueError('Invalid EVN origin')
    headers={'Content-Type':'application/json','Accept':'application/json','User-Agent':'okhttp/4.12.0'}
    if token:headers['Authorization']='Bearer '+token
    req=urllib.request.Request(url,data=json.dumps(payload).encode() if payload is not None else None,headers=headers)
    data=request_json(req, timeout=30)
    if not isinstance(data,dict) or not data.get('success'):raise ValueError('EVN response unsuccessful')
    return data['data']

class Client:
    def __init__(self,account,auth_path=None):
        if not isinstance(account,str) or not account.isalnum():raise ValueError('Invalid account')
        root=json.loads(Path(auth_path or AUTH).read_text());self.secret=root.get('accounts',{}).get(account,root)
        if self.secret.get('customer_id')!=account:raise ValueError('EVN account mismatch')
        self.account=account;self.token=None;self._login()
    def _login(self,force=False):
        key=(self.secret['username'],hashlib.sha256(self.secret['password'].encode()).digest())
        with _LOCK:
            cached=_SESSIONS.get(key)
            if force or not cached or cached['until']<time.monotonic():
                data=_json('https://cskh.evn.com.vn/cskh/v1/auth/login',{'username':self.secret['username'],'password':self.secret['password'],'deviceInfo':{'deviceId':'ha-native-session','deviceType':'Android/HomeAssistant'}})
                cached={'token':data['accessToken'],'identity':(data.get('data') or {}).get('maKhang'),'until':time.monotonic()+1200}
                _SESSIONS[key]=cached
            token=cached['token']
            if cached['identity']!=self.account:
                row=_json('https://cskh.evn.com.vn/cskh/v1/user/swich/'+self.account,token=token)
                identity=(row.get('data') or {}).get('maKhang')
                if identity and identity!=self.account:raise ValueError('EVN switched identity mismatch')
                token=row['accessToken']
            self.token=token
    def request(self,url,payload=None):
        for attempt in range(2):
            try:return _json(url,payload,self.token)
            except urllib.error.HTTPError as error:
                if error.code!=401 or attempt:raise
                self._login(force=True)
