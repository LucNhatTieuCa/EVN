"""Exercise the flow and serialized setup with mocked HA boundaries, no EVN calls."""
import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
import test_runtime

class BaseFlow:
    def __init_subclass__(cls, **kwargs):super().__init_subclass__()
    def _async_current_entries(self):return self.hass.entries
    async def async_set_unique_id(self,value):self.unique_id=value
    def _abort_if_unique_id_configured(self):
        assert not any(e.data.get('customer_id')==self.unique_id for e in self.hass.entries)
    def async_create_entry(self,**kw):return {'type':'create_entry',**kw}
    def async_abort(self,**kw):return {'type':'abort',**kw}
    def async_show_progress(self,**kw):return {'type':'progress',**kw}
    def async_show_progress_done(self,**kw):return {'type':'progress_done',**kw}
    def async_show_form(self,**kw):return {'type':'form',**kw}

class FakeHass:
    def __init__(self):
        self.entries=[types.SimpleNamespace(data={'customer_id':'PCEXIST12345'})]
        self.config=types.SimpleNamespace(path=lambda:'/tmp/evn-onboarding-test-not-written')
        self.data={}
    async def async_add_executor_job(self,fn,*args):return fn(*args)
    def async_create_task(self,coro):return asyncio.create_task(coro)

class OnboardingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        ha=types.ModuleType('homeassistant');ha.config_entries=types.SimpleNamespace(ConfigFlow=BaseFlow,OptionsFlow=BaseFlow)
        helpers=types.ModuleType('homeassistant.helpers');helpers.selector=types.SimpleNamespace();helpers.config_validation=types.SimpleNamespace(config_entry_only_config_schema=lambda domain:{})
        ce=types.ModuleType('homeassistant.config_entries');ce.ConfigEntry=object
        core=types.ModuleType('homeassistant.core');core.HomeAssistant=object
        vol=types.ModuleType('voluptuous')
        cred=types.ModuleType('evn_test.credentials')
        class CredentialsError(Exception):
            def __init__(self,code):self.code=code
        cred.CredentialsError=CredentialsError
        self.saved=[]
        cred.discover_accounts=lambda u,p:[{'customer_id':'PCEXIST12345','name':'Existing'},{'customer_id':'PCDEMO12345','name':'Demo'},{'customer_id':'PCDEMO67890','name':'Demo 2'}]
        cred.save_credentials=lambda u,p,accounts:self.saved.append(list(accounts))
        self.patch=patch.dict(sys.modules,{'homeassistant':ha,'homeassistant.helpers':helpers,'homeassistant.config_entries':ce,'homeassistant.core':core,'voluptuous':vol,'evn_test.credentials':cred})
        self.patch.start()
        spec=importlib.util.spec_from_file_location('evn_test.config_flow',test_runtime.ROOT/'config_flow.py');self.flowmod=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.flowmod)
    async def asyncTearDown(self):self.patch.stop()
    async def test_discover_all_skip_existing_and_no_password_in_entry(self):
        flow=self.flowmod.EVNConfigFlow();flow.hass=FakeHass()
        progress=await flow.async_step_credentials({'username':'fixture','password':'fixture-only'})
        self.assertEqual(progress['type'],'progress')
        task=flow._connect_task
        again=await flow.async_step_connect();self.assertIs(flow._connect_task,task)
        await task
        result=await flow.async_step_register_customers()
        self.assertEqual(result['data']['customer_id'],'PCDEMO12345')
        self.assertEqual(result['data']['linked_customers'],['PCDEMO67890'])
        self.assertEqual(self.saved,[['PCEXIST12345','PCDEMO12345','PCDEMO67890']])
        self.assertNotIn('password',result['data']);self.assertNotIn('password',flow._user_input)
    async def test_setup_serializes_customer_sensor_initialization(self):
        spec=importlib.util.spec_from_file_location('evn_test.bootstrap',test_runtime.ROOT/'__init__.py',submodule_search_locations=None);bootstrap=importlib.util.module_from_spec(spec);spec.loader.exec_module(bootstrap)
        hass=FakeHass();active=0;maximum=0;completed=[]
        async def setup(hass,entry):
            nonlocal active,maximum
            active+=1;maximum=max(maximum,active)
            await asyncio.sleep(.005)
            completed.append(entry);active-=1;return True
        with patch.object(bootstrap,'_async_setup_entry',setup):
            await asyncio.gather(*(bootstrap.async_setup_entry(hass,n) for n in range(4)))
        self.assertEqual(maximum,1);self.assertEqual(completed,[0,1,2,3])

if __name__=='__main__':unittest.main()
