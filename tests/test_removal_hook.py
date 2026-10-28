import sys,types,asyncio,tempfile,unittest,threading
from pathlib import Path
from unittest.mock import patch,AsyncMock
import importlib
pkg=types.ModuleType('hook_test');pkg.__path__=[str(Path(__file__).resolve().parents[1] / 'custom_components/evn')];sys.modules['hook_test']=pkg
module=importlib.import_module('hook_test.removal')
class HookTests(unittest.IsolatedAsyncioTestCase):
 async def test_last_removes_store_entities_and_preserves_source(self):
  await self.run_case()
 async def test_verified_legacy_helper_is_removed(self):
  await self.run_case(legacy=True)
 async def test_user_helper_is_preserved_even_if_mapping_mentions_it(self):
  await self.run_case(legacy=True,foreign=True)
 async def run_case(self,legacy=False,foreign=False):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);(root/'evnvn').mkdir();(root/'evnvn'/'fixture').write_text('private')
   owned=types.SimpleNamespace(entity_id='sensor.evn_fixture',platform='evn')
   registry=types.SimpleNamespace(async_remove=lambda e:removed.append(e))
   removed=[];states=[];store=types.SimpleNamespace(async_remove=AsyncMock(),async_save=AsyncMock())
   manager=types.SimpleNamespace(detach=AsyncMock(),store=store,lock=asyncio.Lock(),data={'accounts':{'PCDEMOA':{'source':'sensor.physical'}},'names':{'PCDEMOA':'alias'}},cache={},electric_cache={},series_cache={},live_points={})
   helper_entity=types.SimpleNamespace(entity_id='sensor.old_derived',platform='utility_meter')
   helper=types.SimpleNamespace(domain='utility_meter',title='User helper' if foreign else 'EVN PCDEMOA Electric Meter Thang',options={'source':'sensor.physical'})
   remove_helper=AsyncMock()
   if legacy:manager.data['accounts']['PCDEMOA'].update({'legacy_entry_id':'legacy-entry','legacy_meter_entity':'sensor.old_derived'})
   er=types.SimpleNamespace(async_get=lambda h:registry,async_entries_for_config_entry=lambda reg,e:[helper_entity] if e=='legacy-entry' else [owned])
   helpers=types.ModuleType('homeassistant.helpers');helpers.entity_registry=er
   storage=types.ModuleType('homeassistant.helpers.storage');storage.Store=lambda *a,**k:store
   creds=types.ModuleType('hook_test.credentials');creds.AUTH=root/'evnvn/private/credentials.json';creds._LOCK=threading.Lock()
   meter=types.ModuleType('hook_test.meter_comparison');meter.KEY='npc_meter_comparison'
   queued=[]
   recorder_module=types.ModuleType('homeassistant.components.recorder')
   def clear(ids,*,on_done):
    queued.extend(ids);on_done()
   recorder_module.get_instance=lambda h:types.SimpleNamespace(async_clear_statistics=clear)
   async def executor(func,*args):return func(*args)
   hass=types.SimpleNamespace(loop=asyncio.get_running_loop(),data={'npc_meter_comparison':manager},config=types.SimpleNamespace(path=lambda *p:str(root.joinpath(*p))),config_entries=types.SimpleNamespace(async_entries=lambda d:[],async_get_entry=lambda e:helper if e=='legacy-entry' else None,async_remove=remove_helper),states=types.SimpleNamespace(async_remove=lambda e:states.append(e)),services=types.SimpleNamespace(has_service=lambda *a:True,async_call=AsyncMock()),async_add_executor_job=executor)
   entry=types.SimpleNamespace(entry_id='fixture-entry',data={'customer_id':'PCDEMOA'})
   with patch.dict(sys.modules,{'homeassistant':types.ModuleType('homeassistant'),'homeassistant.components':types.ModuleType('homeassistant.components'),'homeassistant.components.recorder':recorder_module,'homeassistant.helpers':helpers,'homeassistant.helpers.storage':storage,'hook_test.credentials':creds,'hook_test.meter_comparison':meter}):
    await module.async_remove(hass,entry)
   if legacy and not foreign:remove_helper.assert_awaited_once_with('legacy-entry')
   else:remove_helper.assert_not_awaited()
   self.assertEqual(queued,['sensor.evn_fixture']+(['sensor.old_derived'] if legacy and not foreign else []));self.assertFalse((root/'evnvn').exists());self.assertEqual(removed,['sensor.evn_fixture']);self.assertEqual(states,['sensor.evn_fixture']);store.async_remove.assert_awaited_once();self.assertEqual(manager.data,{'accounts':{},'archive':[]});manager.detach.assert_awaited_once_with('PCDEMOA')
if __name__=='__main__':unittest.main(verbosity=2)
