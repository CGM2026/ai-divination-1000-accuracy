"""阶段冻结、抽牌、评分和可读报告；预测文本由独立角色生成。"""
import argparse, hashlib, importlib.util, json, math, shutil, sys
from pathlib import Path
from datetime import datetime, timezone
R=Path(__file__).resolve().parent
SK=R/'skills/cgm-three-card-divination'
def read(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def save(p,x):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8') as f:json.dump(x,f,ensure_ascii=False,indent=2)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def freeze(directory, label):
    d=Path(directory)
    files={str(p.relative_to(d)):sha(p) for p in sorted(d.rglob('*')) if p.is_file() and '__pycache__' not in str(p)}
    save(R/'freezes'/f'{label}.json',dict(at=datetime.now(timezone.utc).isoformat(),directory=str(d),files=files))
def prepare(start,end,version):
    rows=read(R/'public/development.json')+read(R/'public/holdout.json')
    spec=importlib.util.spec_from_file_location('draw',SK/'scripts/draw.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    out=[]
    for c in rows:
        n=int(c['id'][1:])
        if not start<=n<=end:continue
        src=R/'inputs'/f"{c['id']}.json"
        if not src.exists():save(src,c)
        rec=m.draw(src,R/'draws'/f"{c['id']}.json")
        out.append(dict(**c,cards=rec['cards'],version=version))
    save(R/'packets'/f'{start:03}-{end:03}.json',out)
    dest=R/'versions'/version
    shutil.copytree(SK,dest,ignore=shutil.ignore_patterns('__pycache__'))
    freeze(dest,version)
def validate_predictions(rows,expected,cards=False):
    assert len(rows)==len(expected) and {x['id'] for x in rows}=={x['id'] for x in expected}
    by={x['id']:x for x in expected}
    for p in rows:
        assert p['prediction'] in [0,1] and 0<=p['p_yes']<=1
        assert p['prediction']==int(p['p_yes']>=.5)
        assert p['answer'] and p['rationale']
        if cards:assert p['cards']==by[p['id']]['cards'] and p['version']==by[p['id']]['version']
def stats(rows):
    n=len(rows); k=sum(x['correct'] for x in rows);p=k/n;z=1.96
    a=(p+z*z/(2*n))/(1+z*z/n);b=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/(1+z*z/n)
    return dict(n=n,correct=k,accuracy=p,wilson95=[a-b,a+b],brier=sum((x['p_yes']-x['outcome'])**2 for x in rows)/n)
def score(start,end):
    packet=read(R/'packets'/f'{start:03}-{end:03}.json')
    path=R/'predictions'/f'{start:03}-{end:03}.json';pred=read(path)
    validate_predictions(pred,packet,True)
    save(R/'freezes'/f'predictions-{start:03}-{end:03}.json',dict(at=datetime.now(timezone.utc).isoformat(),sha256=sha(path)))
    endings={x['id']:x for x in read(R/'author_private/stories.json')}
    rows=[dict(**x,outcome=endings[x['id']]['outcome'],ending=endings[x['id']]['ending'],correct=x['prediction']==endings[x['id']]['outcome']) for x in pred]
    save(R/'scores'/f'{start:03}-{end:03}.json',dict(summary=stats(rows),rows=rows))
    print(json.dumps(stats(rows),ensure_ascii=False))
def report():
    public=read(R/'public/development.json')+read(R/'public/holdout.json');by={x['id']:x for x in public}
    base=read(R/'baseline/predictions.json');validate_predictions(base,public);bb={x['id']:x for x in base}
    batches=[read(R/'scores'/f'{s:03}-{e:03}.json') for s,e in [(1,20),(21,40),(41,60),(61,100)]]
    rows=[x for b in batches for x in b['rows']]
    for r in rows:
        r['baseline']=bb[r['id']];r['baseline_correct']=bb[r['id']]['prediction']==r['outcome']
    def bst(sub):return stats([dict(p_yes=x['baseline']['p_yes'],correct=x['baseline_correct'],outcome=x['outcome']) for x in sub])
    summary={}
    for label,sub in [('development',rows[:60]),('holdout',rows[60:]),('all_descriptive',rows)]:
        summary[label]=dict(cards=stats(sub),baseline=bst(sub),cards_only_correct=sum(x['correct'] and not x['baseline_correct'] for x in sub),baseline_only_correct=sum(not x['correct'] and x['baseline_correct'] for x in sub),outcome_yes=sum(x['outcome'] for x in sub),majority_reference=max(sum(x['outcome'] for x in sub),len(sub)-sum(x['outcome'] for x in sub))/len(sub))
    paired=summary['holdout'];a=paired['cards_only_correct'];b=paired['baseline_only_correct'];n=a+b
    paired['mcnemar_exact_two_sided']=min(1,2*sum(math.comb(n,i) for i in range(min(a,b)+1))/2**n) if n else 1.0
    save(R/'results.json',dict(summary=summary,rows=rows))
    lines=['# 100个故事与预测对照','每个故事的结局都在预测前固定。对/错只按预定二元问题判定；预测叙述的细节没有另行计分。','']
    for r in rows:
        c=by[r['id']];b=r['baseline']
        lines += [f"## {r['id']} · {c['domain']} · {'开发' if c['split']=='development' else '留出检验'}",c['background'],f"**问题：** {c['question']}",f"**判定标准：** {c['yes_definition']}",f"**三张牌：** {'、'.join(r['cards'])}（{r['version']}）",f"**占卜回应：** {r['answer']}",f"**牌义依据：** {r['rationale']}",f"**发生概率：** {r['p_yes']:.0%}；**判定：{'对' if r['correct'] else '错'}**",f"**固定结局：** {r['ending']}",f"**不抽牌对照：** {b['answer']}（发生概率{b['p_yes']:.0%}；{'对' if r['baseline_correct'] else '错'}）",'']
    (R/'100例完整对照.md').write_text('\n\n'.join(lines),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','score','report']);p.add_argument('--start',type=int);p.add_argument('--end',type=int);p.add_argument('--version');a=p.parse_args()
    if a.action=='prepare':prepare(a.start,a.end,a.version)
    elif a.action=='score':score(a.start,a.end)
    else:report()
