"""Local API demonstration. Does not execute imported repository code."""
import json
import time
import httpx

def main():
    with httpx.Client(base_url='http://127.0.0.1:8000/api',timeout=30) as c:
        def post(path,body):
            r=c.post(path,json=body);r.raise_for_status();return r.json()
        w=post('/workspaces',{'interest':'演示：文档处理','role':'Python 后端','skills':'Python','time_budget':'两周','environment':'本地 CPU'})
        wid=w['id'];base='/workspaces/'+wid
        run=post(base+'/analysis-runs',{'url':'https://github.com/repocareer-demo/document-service','demo':True,'idempotency_key':'demo-run'})
        for _ in range(100):
            r=c.get('/runs/'+run['id'],params={'workspace_id':wid}).json()
            if r['status'] not in ('queued','running'):break
            time.sleep(.1)
        if r['status']!='completed':raise RuntimeError(r)
        contribution={'personal_role':'演示人物，非用户真实贡献','problem':'非法编码输入报错不明确','action':'增加编码错误处理与回归用例','tradeoffs':'沿用上游内容哈希缓存，未引入 Redis','state':'implemented','outcome':'没有对比实验，不声称提升'}
        record=post(base+'/contributions',contribution)
        a=post(base+'/artifacts',{'type':'resume','idempotency_key':'demo-resume-1'})
        patch=c.patch('/contributions/'+record['id'],json={**contribution,'outcome':'更正为预估，无实测','expected_version':1,'workspace_id':wid});patch.raise_for_status()
        old=c.get('/artifacts/'+a['id'],params={'workspace_id':wid}).json()
        b=post(base+'/artifacts',{'type':'resume','idempotency_key':'demo-resume-2'})
        print(json.dumps({'workspace_id':wid,'run':r['status'],'old_draft':old['review_status'],'new_draft':b['content']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
