import asyncio,importlib,sys,types,tempfile,sqlite3,json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1] / 'custom_components/evn'
pkg=types.ModuleType('cleanup_test');pkg.__path__=[str(ROOT)];sys.modules['cleanup_test']=pkg
m=importlib.import_module('cleanup_test.removal');database=importlib.import_module('cleanup_test.database')
class RemovalTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name);self.root=self.base/'evnvn';self.auth=self.base/'private'/'evn-cpc.json';self.auth.parent.mkdir();self.a='PCDEMOA';self.b='PCDEMOB';database.ensure_database(str(self.root/'evndata.db'))
  profiles={a:{'customer_id':a,'username':a,'password':'synthetic-only'} for a in [self.a,self.b]};self.auth.write_text(json.dumps({**profiles[self.a],'accounts':profiles}))
  for a in profiles:
   (self.root/'invoices'/a).mkdir(parents=True);(self.root/'invoices'/a/'doc.pdf').write_bytes(b'fixture');(self.root/(a+'_1_2026.png')).write_bytes(b'fixture')
  with sqlite3.connect(self.root/'evndata.db') as db:
   db.execute('CREATE TABLE IF NOT EXISTS npc_pdf_attempts(invoice_row_id INTEGER PRIMARY KEY,status TEXT,retry_after TEXT,checked_at TEXT)')
   for a in profiles:
    db.execute('INSERT INTO daily_consumption(userevn,ngay) VALUES(?,?)',(a,'01-01-2026'));db.execute('INSERT INTO npc_sync_state(account) VALUES(?)',(a,));db.execute('INSERT INTO npc_entity_ids VALUES(?,?)',(a+'_current','sensor.'+a.lower()));db.execute('INSERT INTO npc_invoice_index(account,invoice_id,year,month,org_code,payload,updated_at) VALUES(?,?,2026,1,?,?,?)',(a,a,'DEMO','{}','now'));ident=db.execute('SELECT last_insert_rowid()').fetchone()[0];db.execute('INSERT INTO npc_invoice_files(invoice_row_id,kind,path,sha256,size_bytes,fetched_at) VALUES(?,?,?,?,1,?)',(ident,'pdf',a+'/doc.pdf','fixture','now'));db.execute('INSERT INTO npc_pdf_attempts VALUES(?,?,?,?)',(ident,'saved',None,'now'))
   db.execute("CREATE TRIGGER codex_cpc_PCDEMOA_daily_consumption_DELETE BEFORE DELETE ON daily_consumption WHEN old.userevn='PCDEMOA' BEGIN SELECT RAISE(ABORT,'guard'); END")
 def tearDown(self):self.tmp.cleanup()
 def test_partial_removes_every_owned_row_and_files_preserves_sibling(self):
  m.purge_files(self.root,self.auth,self.a,{self.b})
  with sqlite3.connect(self.root/'evndata.db') as db:
   self.assertEqual(db.execute('SELECT userevn FROM daily_consumption').fetchall(),[(self.b,)]);self.assertEqual(db.execute('SELECT account FROM npc_sync_state').fetchall(),[(self.b,)]);self.assertEqual(db.execute('SELECT count(*) FROM npc_invoice_files').fetchone()[0],1);self.assertEqual(db.execute('SELECT count(*) FROM npc_pdf_attempts').fetchone()[0],1);self.assertEqual(db.execute('SELECT unique_id FROM npc_entity_ids').fetchone()[0],self.b+'_current')
  self.assertFalse((self.root/'invoices'/self.a).exists());self.assertTrue((self.root/'invoices'/self.b/'doc.pdf').exists());self.assertFalse((self.root/(self.a+'_1_2026.png')).exists());d=json.loads(self.auth.read_text());self.assertEqual(set(d['accounts']),{self.b});self.assertEqual(d['customer_id'],self.b)
 def test_last_removes_all_and_is_idempotent_without_touching_neighbor(self):
  neighbor=self.base/'other.db';neighbor.write_bytes(b'untouched');key=self.auth.parent/'evn-credentials-history.key';key.write_bytes(b'fixture')
  m.purge_files(self.root,self.auth,self.a,set());m.purge_files(self.root,self.auth,self.a,set());self.assertFalse(self.root.exists());self.assertFalse(self.auth.exists());self.assertFalse(key.exists());self.assertEqual(neighbor.read_bytes(),b'untouched')
 def test_invalid_account_and_symlink_are_rejected(self):
  with self.assertRaises(ValueError):m.purge_files(self.root,self.auth,'../PCX',set())
  link=self.base/'linked';link.symlink_to(self.root,target_is_directory=True)
  with self.assertRaises(ValueError):m.purge_files(link,self.auth,self.a,set())
  self.assertTrue((self.root/'evndata.db').exists())
if __name__=='__main__':unittest.main(verbosity=2)
