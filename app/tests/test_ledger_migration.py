from pathlib import Path
from contextlib import closing
import hashlib,json,sqlite3,tempfile,unittest
from types import SimpleNamespace
from unittest.mock import patch
from asc import settings,ssh_jobs as jobs,manual_client as manual

class LedgerMigration(unittest.TestCase):
    def test_configuration_has_no_environment_or_missing_path_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); db=root/'ledger.sqlite'
            with closing(sqlite3.connect(db)) as connection, connection:connection.execute('create table existing(value)')
            config=root/'services.toml';config.write_text('[paths]\nledger_db="'+str(db)+'"\n')
            with patch.dict('os.environ',{'AUTOSCRIBE_LEDGER_DB':'/obsolete/ledger'}):
                self.assertEqual(settings.ledger_path(config),db)
            config.write_text('[paths]\nledger_db="'+str(root/'missing')+'"\n')
            with self.assertRaises(FileNotFoundError):settings.ledger_path(config)
            self.assertFalse((root/'missing').exists())

    def test_applied_cleanup_requires_ack_and_retries_after_runtime_expiry(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);ledger=root/'ledger.sqlite';jobs.initialize(ledger)
            identity='400e11b6-4d77-4d18-8787-e2c309dc5a92';digest='a'*64
            folder=root/identity;folder.mkdir();data=b'retained response\n';checksum=hashlib.sha256(data).hexdigest()
            (folder/'response.ndjson').write_bytes(data)
            with closing(sqlite3.connect(ledger)) as db, db:
                db.execute(manual.APPLICATIONS)
                db.execute('INSERT INTO ssh_jobs(dispatch_id,record_id,call_id,package_sha256,state,accepted_at,response_sha256) VALUES(?,?,?,?,?,?,?)',(identity,'record','call',digest,'applied',1,checksum))
            with patch.object(jobs,'ROOT',root):
                with self.assertRaises(ValueError):jobs.cleanup(ledger,identity,digest,checksum,None)
                self.assertTrue(folder.exists())
                receipt=json.dumps({'file_sha256':'b'*64,'git_commit':'c'*40},sort_keys=True,separators=(',',':'))
                with closing(sqlite3.connect(ledger)) as db, db:
                    db.execute('INSERT INTO client_applications VALUES(?,?,?,?,?,?,?)',(identity,'writeback','d'*64,'e'*64,1,2,receipt))
                with patch.object(jobs.Call,'load',side_effect=jobs.MissingRecord('expired')):
                    with self.assertRaises(ValueError):jobs.cleanup(ledger,identity,digest,'f'*64,None)
                    self.assertTrue(folder.exists())
                    result=jobs.cleanup(ledger,identity,digest,checksum,None)
                    self.assertEqual(result['state'],'cleaned');self.assertFalse(folder.exists())
                    self.assertEqual(jobs.cleanup(ledger,identity,digest,checksum,None)['state'],'cleaned')
                request=dict(mode='writeback',intent='d'*64,target='e'*64,response_sha256=checksum,receipt=json.loads(receipt))
                self.assertEqual(manual.application(ledger,'ack',identity,request)['application']['applied_at'],2)
                request['target']='f'*64
                with self.assertRaises(ValueError):manual.application(ledger,'ack',identity,request)
