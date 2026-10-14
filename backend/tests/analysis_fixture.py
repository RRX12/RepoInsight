import json
from backend.app.analysis_contract import GenerationContext
SHA='a'*40
MATERIAL={'workspace_id':'offline','snapshot_id':'s','commit':SHA,'repo':'example/demo','role':'AI工程师','jd':'多轮记忆','jd_version_id':'j'}
def claim(i='c1',support='insufficient'):
 return {'id':i,'statement':'角色记忆按版本更新，过期更新被拒绝。','evidence_ids':['source:memory'],'support':support,'implementation_state':'implemented','attribution':'upstream','validation_level':'unknown'}
def candidate(i='n1',cid='c1'):
 return {'candidate_id':i,'title':'版本化记忆','mechanism':'拒绝过期更新','claim_ids':[cid],'requirement_ids':['r1'],'reason':'状态连续性'}
def context():
 return GenerationContext(workspace_id='offline',snapshot_id='s',commit_sha=SHA,revision_status='resolved',role='AI工程师',jd_version_id='j',target_origin='jd',material_fingerprint='test')
class Stub:
 base='https://fixture';model='contract-stub';usage=[]
 def __init__(self):self.calls=[]
 def close(self):pass
 def __call__(self,p):
  stage=p.split('\n',1)[0];self.calls.append((stage,p))
  if stage=='PROJECT_CONTEXT':d={'audience':'创作者','background':'角色记忆','value_summary':'保存角色经历'}
  elif stage=='JD_PLAN':d={'requirements':[{'requirement_id':'r1','description':'多轮记忆','origin':'role_inferred' if '"jd_sources": {}' in p else 'jd','question':'如何延续角色状态？','search_terms':['memory','记忆'],'queries':['memory revision','过期更新拒绝'],'jd_source_ids':list(json.loads(p.split('\nJSON schema:')[0].split('\n')[-1])['jd_sources'])[:6]}]}
  elif stage in ('INVESTIGATE','SYNTHESIZE'):d={'claims':[claim(),claim('c2')],'candidates':[candidate(),candidate('n2','c2')]}
  elif stage.startswith('CLAIM_VERIFY'):d={'claims':[claim(support='supported'),claim('c2',support='supported')]}
  else:raise AssertionError(stage)
  return json.dumps(d,ensure_ascii=False)
