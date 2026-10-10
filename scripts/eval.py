"""Same provider/model, three optional memory inputs; no invented quality scores."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.app.providers import ModelProvider

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check-fixtures',action='store_true');parser.add_argument('--output',default='data/eval-results.jsonl');args=parser.parse_args()
    cases=[json.loads(line) for line in (Path(__file__).resolve().parents[1]/'fixtures/eval.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    if args.check_fixtures:
        for case in cases:
            assert all(k in case for k in ('id','messages','summary','structured','expected_claims','forbidden_claims'))
            assert isinstance(case['structured']['contributions'],list)
        print(f'{len(cases)} labeled fixtures valid; no model evaluation executed.');return
    model=ModelProvider()
    if model.demo: raise SystemExit('真实评测需要 REPOCAREER_DEMO=false 和 OPENAI_API_KEY。未调用模型，不生成比较结论。可使用 --check-fixtures 检查标注格式。')
    target=Path(args.output);target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('w',encoding='utf-8') as file:
        for case in cases:
            for mode,key in [('direct','messages'),('summary','summary'),('structured','structured')]:
                result=model.complete({'task':'请用 reply 输出中文项目简历要点，仅使用已实现个人贡献，缺证据数字不写。','material':case[key],'jd':'Python 后端，输入校验与可复现测试'})
                text=result['reply']
                file.write(json.dumps({'case_id':case['id'],'path':mode,'output':text,'usage':result.get('usage'),'elapsed_seconds':result.get('elapsed_seconds'),
                    'lexical_missing':[x for x in case['expected_claims'] if x not in text], 'lexical_unsupported':[x for x in case['forbidden_claims'] if x in text],
                    'human_scores':{'omission':None,'unsupported_claims':None,'correction_residue':None,'jd_relevance_1_to_5':None},
                    'limitations':'summary 使用人工固定摘要；词面检查不代表语义质量，需盲审；不得由此宣称产品效果提升。'},ensure_ascii=False)+'\n');file.flush()
    print('Saved real outputs for blind human review:',target)
if __name__=='__main__':main()
