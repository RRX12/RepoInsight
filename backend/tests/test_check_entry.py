import subprocess
import sys
from scripts import check as entry


def test_missing_package_manager_is_a_failure_not_a_skip(monkeypatch):
    monkeypatch.setattr(sys,'argv',['check.py'])
    monkeypatch.setattr(entry.shutil,'which',lambda name:None)
    assert entry.main()==1


def test_failed_step_stops_same_entry_and_returns_failure(monkeypatch):
    monkeypatch.setattr(sys,'argv',['check.py','--e2e'])
    monkeypatch.setattr(entry.shutil,'which',lambda name:'pnpm')
    calls=[]
    def fail(args,**kwargs):
        calls.append(args)
        assert kwargs['check'] is True
        assert kwargs['env']['REPOCAREER_DATA']!=str(entry.ROOT/'data')
        raise subprocess.CalledProcessError(7,args)
    monkeypatch.setattr(entry.subprocess,'run',fail)
    assert entry.main()==7 and len(calls)==1
