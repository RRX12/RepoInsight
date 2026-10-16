"""Manual quality review entry. Default is offline rubric only, never an API call."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--allow-paid',action='store_true');p.add_argument('--workspace-id');p.add_argument('--snapshot-id');p.add_argument('--output',type=Path)
    args=p.parse_args()
    rubric=['依据准确性','值得做的方向覆盖','取舍合理性','步骤可执行性','成本']
    if not args.allow_paid:
        print(json.dumps({'mode':'offline_rubric_only','quality_verified':False,'rubric':rubric,'cases':json.loads((ROOT/'fixtures/optimization-advisor/cases.json').read_text(encoding='utf-8'))},ensure_ascii=False,indent=2));return
    if not args.workspace_id or not args.snapshot_id or not args.output:p.error('Real calls require --workspace-id, --snapshot-id and --output; may incur model/search/embedding costs.')
    from backend.app.db import Session
    from backend.app.project_inputs import collect_project
    from backend.app.optimization_review import generate
    with Session() as s:
        snap,material,fingerprint=collect_project(s,args.workspace_id)
        if snap.id!=args.snapshot_id:p.error('Snapshot must be the current explicitly chosen fixed version.')
    def check():
        with Session() as s:
            if collect_project(s,args.workspace_id)[2]!=fingerprint:raise ValueError('inputs_changed')
    report,usage=generate(snap,material,lambda *a:None,check)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps({'report':report,'usage':usage,'rubric':rubric,'quality_verified':False,'note':'需人工逐项对照同SHA/JD/约束；未发布Run或Improvement'},ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':main()
