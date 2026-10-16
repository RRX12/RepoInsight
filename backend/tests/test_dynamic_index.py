import threading
import pytest
from scripts.deepwiki_raw_index import Index
from scripts.wiki_rag_contract import settings_from_env

SHA='a'*40

def test_bounded_parallel_unique_inputs_and_complete_reuse(tmp_path):
    gate=threading.Barrier(2);lock=threading.Lock();calls=[];active=0;peak=0;events=[]
    def embed(text):
        nonlocal active,peak
        with lock:active+=1;peak=max(peak,active);calls.append(text)
        gate.wait(timeout=2)
        with lock:active-=1
        return [1.,2.]
    files={f'{i}.py':f'VALUE={i}\n' for i in range(4)};files['duplicate.py']=files['0.py']
    index=Index(tmp_path,'fp',embed)
    first=index.prepare('o/r',SHA,files,4,concurrency=2,batch_size=2,progress=events.append)
    assert peak==2 and len(calls)==4 and len(first['manifest']['chunks'])==5
    assert first['usage']['code_calls']==4 and events[-1]['remaining_new_vectors']==0
    second=index.prepare('o/r',SHA,files,0,concurrency=2,progress=events.append)
    assert second['reused'] and len(calls)==4 and events[-1]['phase']=='reused'

def test_failed_window_resume_only_missing_and_cap_remains_hard(tmp_path):
    files={'a.py':'A=1','b.py':'B=2','c.py':'C=3'};calls=[];failed=[True];events=[]
    def embed(text):
        calls.append(text)
        if text=='B=2' and failed[0]:raise ValueError('embedding_failed')
        return [1.,2.]
    index=Index(tmp_path,'fp',embed)
    with pytest.raises(ValueError,match='budget'):index.prepare('o/r',SHA,files,2,progress=events.append)
    assert not calls
    with pytest.raises(ValueError,match='embedding_failed'):index.prepare('o/r',SHA,files,3,batch_size=1,progress=events.append)
    assert not list((tmp_path/'manifests').glob('*.json')) and events[-1]['phase']=='stopped'
    assert index.dry_run('o/r',SHA,files)['required_new_vectors']==2
    failed[0]=False;before=len(calls)
    result=index.prepare('o/r',SHA,files,2,batch_size=1)
    assert calls[before:]==['B=2','C=3'] and result['usage']['code_calls']==2

def test_cancel_discards_late_vector_and_does_not_publish_manifest(tmp_path):
    cancelled=[False];calls=[]
    def check():
        if cancelled[0]:raise ValueError('cancelled')
    def embed(text):calls.append(text);cancelled[0]=True;return [1.,2.]
    index=Index(tmp_path,'fp',embed)
    with pytest.raises(ValueError,match='cancelled'):index.prepare('o/r',SHA,{'a.py':'A=1','b.py':'B=2'},2,batch_size=1,check=check)
    assert len(calls)==1 and not list((tmp_path/'vectors').glob('*.json')) and not list((tmp_path/'manifests').glob('*.json'))

def test_auto_settings_does_not_depend_on_old_zero_budget(monkeypatch):
    monkeypatch.setenv('WIKI_RAG_INDEX_MODE','auto');monkeypatch.setenv('WIKI_RAG_MAX_NEW_VECTORS','0');monkeypatch.setenv('WIKI_RAG_AUTO_VECTOR_LIMIT','12000')
    config=settings_from_env()['budgets']
    assert config['index_mode']=='auto' and config['auto_vector_limit']==12000 and config['max_new_vectors']==0
