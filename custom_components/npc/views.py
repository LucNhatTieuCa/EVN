"""Authenticated financial views with one verified pricing engine."""
import json,sqlite3,logging,mimetypes
from datetime import datetime,timedelta
from pathlib import Path
from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.util import dt as dt_util
from .const import DOMAIN,CONF_CUSTOMER_ID
from .paths import data_path
DB_PATH=str(data_path("evndata.db"))
from .pricing import number,day,read_prices
_LOGGER=logging.getLogger(__name__)

def _configured(hass,account):
    return any(e.data.get(CONF_CUSTOMER_ID)==account and e.disabled_by is None for e in hass.config_entries.async_entries(DOMAIN))

def monthly_payload(account):
    result={'SanLuong':[],'TienDien':[],'MissingInvoices':[]}
    with sqlite3.connect('file:'+DB_PATH+'?mode=ro',uri=True,timeout=10) as db:
        rows=db.execute('SELECT thang,tien_dien,san_luong_kwh,nam FROM monthly_bill WHERE userevn=? ORDER BY nam,thang',(account,)).fetchall()
    for month,money,used,year in rows:
        base={'Tháng':int(month),'Năm':int(year)}
        production=number(used);fee=number(money)
        if production is not None:result['SanLuong'].append({**base,'Điện tiêu thụ (KWh)':production})
        if fee is None:result['MissingInvoices'].append(base)
        else:result['TienDien'].append({**base,'Tiền Điện':fee})
    return result

def daily_payload(account,now):
    from .meter_comparison import _official
    current=_official(account,now)
    prices=read_prices(account,{'declared_period_start':now.replace(day=1).isoformat(),'initial_reading':current.get('initial_reading'),'read_at':current.get('cutoff')})
    with sqlite3.connect('file:'+DB_PATH+'?mode=ro',uri=True,timeout=10) as db:
        rows=db.execute('SELECT ngay,chi_so,dien_tieu_thu_kwh FROM daily_consumption WHERE userevn=?',(account,)).fetchall()
    result=[];first=now.date()-timedelta(days=365)
    for raw,index,used in rows:
        date=day(raw);value=number(used)
        if date is None or not first<=date<=now.date() or value is None:continue
        price=prices['daily'].get(date.strftime('%d-%m-%Y'),{})
        result.append({'Ngày':date.strftime('%d-%m-%Y'),'Điện tiêu thụ (kWh)':value,'Tiền điện (VND)':price.get('daily_cost_vnd'),'CHISO':number(index)})
    result.sort(key=lambda row:day(row['Ngày']))
    return result

class EVNPingView(HomeAssistantView):
    url='/api/npc/ping'
    name='api:npc:ping'
    requires_auth=False
    def __init__(self,hass):self.hass=hass
    async def get(self,request):return web.json_response({'status':'ok','message':'NPC API is running'})

class EVNStaticView(HomeAssistantView):
    """Serve static files from webui directory."""

    url = "/npc-monitor/{filename:.*}"
    name = "npc_monitor:static"
    requires_auth = False

    def __init__(self, webui_path: str, hass=None):
        """Initialize the static file server.
        
        Args:
            webui_path: Absolute path to the webui directory
            hass: Home Assistant instance for async operations
        """
        self.webui_path = Path(webui_path)
        self.hass = hass
        _LOGGER.info("EVNStaticView initialized with path: %s", self.webui_path)

    async def get(self, request, filename: str):
        """Serve a static file.
        
        Args:
            request: The HTTP request
            filename: Relative path to the file (e.g., "index.html" or "assets/js/main.js")
        """
        # Default to index.html if no filename or directory requested
        if not filename or filename.endswith('/'):
            filename = filename + 'index.html' if filename else 'index.html'

        # Construct full file path
        file_path = self.webui_path / filename
        
        # Security check: ensure the resolved path is within webui_path
        try:
            file_path = file_path.resolve()
            if not file_path.is_relative_to(self.webui_path.resolve()):
                _LOGGER.debug("Attempted path traversal: %s", filename)
                return web.Response(status=403, text="Forbidden")
        except Exception as ex:
            _LOGGER.debug("Error resolving path %s: %s", filename, str(ex))
            return web.Response(status=400, text="Bad Request")

        # Check if file exists
        if not file_path.is_file():
            _LOGGER.debug("File not found: %s", file_path)
            return web.Response(status=404, text="Not Found")

        # Determine content type
        content_type, _ = mimetypes.guess_type(str(file_path))
        if content_type is None:
            content_type = "application/octet-stream"
        
        # Prepare headers
        headers = {
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
        
        # Add charset for text/* and application/javascript
        if content_type.startswith("text/") or content_type == "application/javascript":
            headers["Content-Type"] = f"{content_type}; charset=utf-8"
        else:
            headers["Content-Type"] = content_type

        # Read file asynchronously
        try:
            hass = request.app["hass"]
            content = await hass.async_add_executor_job(
                lambda: file_path.read_bytes()
            )
            
            return web.Response(
                body=content,
                headers=headers
            )
        except Exception as ex:
            _LOGGER.debug("Error reading file %s: %s", file_path, str(ex))
            return web.Response(status=500, text="Internal Server Error")

class EVNOptionsView(HomeAssistantView):
    url='/api/npc/options'
    name='api:npc:options'
    requires_auth=True
    def __init__(self,hass):self.hass=hass
    async def get(self,request):
        from .meter_comparison import KEY
        from .customer_names import official_names,label
        entries=[e for e in self.hass.config_entries.async_entries(DOMAIN) if e.disabled_by is None and e.data.get(CONF_CUSTOMER_ID)]
        codes=[e.data[CONF_CUSTOMER_ID] for e in entries]
        official=await self.hass.async_add_executor_job(official_names,codes)
        manager=self.hass.data.get(KEY)
        aliases=manager.data.get('names',{}) if manager else {}
        accounts=[{'userevn':a,'id':a,'customer_id':a,'ngaydauky':1,**label(a,aliases,official)} for a in codes]
        return web.json_response({'accounts_json':json.dumps(accounts)})

class _AccountView(HomeAssistantView):
    requires_auth=True
    def __init__(self,hass):self.hass=hass
    async def execute(self,account,func,*args):
        if not _configured(self.hass,account):raise web.HTTPNotFound()
        try:return web.json_response(await self.hass.async_add_executor_job(func,account,*args),headers={'Cache-Control':'private, no-store'})
        except Exception:
            _LOGGER.warning('EVN view could not read stored data for %s',account)
            return web.json_response({'error':'Không đọc được dữ liệu EVN đã lưu'},status=503)

class EVNMonthlyDataView(_AccountView):
    url='/api/npc/monthly/{account}'
    name='api:npc:monthly'
    async def get(self,request,account):return await self.execute(account,monthly_payload)

class EVNDailyDataView(_AccountView):
    url='/api/npc/daily/{account}'
    name='api:npc:daily'
    async def get(self,request,account):return await self.execute(account,daily_payload,dt_util.now())

class EVNCurrentPeriodView(_AccountView):
    url='/api/npc/current/{account}'
    name='api:npc:current'
    async def get(self,request,account):
        def read(code):
            from .meter_comparison import _official
            current=_official(code,dt_util.now())
            return {'account':code,'tieu_thu_ky_nay':current['kwh'],'tien_dien_ky_nay':current['estimated_vnd'],
                'ngay_dau_ky':current.get('period_start'),'ngay_cap_nhat':current.get('fetched_at')}
        return await self.execute(account,read)
