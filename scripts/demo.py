"""Local project-analysis demo; synthetic output, no paid model or repository execution."""
import argparse,json,time
import httpx

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--url',default='https://github.com/AsyncFuncAI/deepwiki-open');args=parser.parse_args()
    with httpx.Client(base_url='http://127.0.0.1:8000/api',timeout=30) as c:
        def post(path,body):
            r=c.post(path,json=body);r.raise_for_status();return r.json()
        w=post('/workspaces',{'interest':'演示：项目理解','role':'项目工程优化'});wid=w['id'];base='/workspaces/'+wid
        snap=post(base+'/repository-link',{'url':args.url})
        run=post(base+'/architecture-runs',{'snapshot_id':snap['id'],'demo':True,'idempotency_key':'demo-analysis'})
        for _ in range(100):
            response=c.get('/runs/'+run['id'],params={'workspace_id':wid});response.raise_for_status();r=response.json()
            if r['status'] not in ('queued','running'):break
            time.sleep(.1)
        if r['status']!='completed':raise RuntimeError(r)
        print(json.dumps({'workspace_id':wid,'run':r['status'],'mode':'demo: 不是实际链接仓库分析','overview':r['result']['report']['overview'],'directions':r['result']['report']['directions']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
