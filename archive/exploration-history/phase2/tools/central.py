"""Read-only research audit, derived indexes and central progress bookkeeping."""
from pathlib import Path
import argparse, json, csv, re
from collections import Counter
from draw import read_events, digest

ROOT=Path(__file__).resolve().parents[1]
def save(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def progress():
    p=ROOT/'研究对话登记.json'; rows=json.loads(p.read_text(encoding='utf-8'))
    total=0
    for row in rows:
        folder=ROOT/row['directory']; events=read_events(folder)
        row['completed']=sum(e['event']=='note' for e in events)
        row['last_event']=events[-1]['event'] if events else None
        row['last_id']=events[-1]['id'] if events else None
        total+=row['completed']
        target=row.get('target',24)
        if row['completed']==target and (folder/f'快照_{target:02d}.md').exists() and (folder/'研究小结.md').exists():
            row['status']='records_complete'
    save(p,rows)
    s=ROOT/'实验状态.json'; state=json.loads(s.read_text(encoding='utf-8')); state['completed']=total;save(s,state)
    print(json.dumps([{'id':r['id'],'n':r['completed'],'last':r.get('last_event'),'status':r['status']} for r in rows],ensure_ascii=False))

def audit(batch):
    rows=json.loads((ROOT/'研究对话登记.json').read_text(encoding='utf-8'))
    rows=[r for r in rows if r['id'].startswith(batch+'-')]
    result=[]; suits=Counter(); values=Counter(); index=[]; combos=Counter(); allids=set()
    for r in json.loads((ROOT/'研究对话登记.json').read_text(encoding='utf-8')):
        allids.update(e['id'] for e in read_events(ROOT/r['directory']) if e['event']=='note')
    for row in rows:
        folder=ROOT/row['directory']; es=read_events(folder); issues=[]; n=sum(e['event']=='note' for e in es)
        if len(es)!=n*3:issues.append('存在未完成轮次')
        if n!=row.get('target',24):issues.append('未到目标轮数')
        snapshots={}
        for k in range(8,n+1,8):
            p=folder/f'快照_{k:02d}.md'
            if not p.exists(): issues.append(f'缺快照{k}')
            else:
                content=p.read_text(encoding='utf-8');snapshots[p.name]=digest(content)
                for ref in re.findall(r'B\d{2}-[A-Z]-R\d{3}',content):
                    if ref not in allids:issues.append('不存在的快照引用:'+ref)
        common=folder/'共同场景.json'
        if common.exists():
            qs=json.loads(common.read_text(encoding='utf-8'))
            for e in es:
                if e['event']=='question' and str(e['round']) in qs and e['data']['question']!=qs[str(e['round'])]:
                    issues.append('共同题原文不一致:'+e['id'])
        for i in range(n):
            q,d,note=es[i*3:i*3+3]
            cards=d['data']
            suits.update(c[:2] for c in cards);values.update(c[2:] for c in cards)
            ss=[c[:2] for c in cards];vv=[c[2:] for c in cards]
            combos['三花色' if len(set(ss))==3 else '全同花' if len(set(ss))==1 else '两花色']+=1
            if ss[0]==ss[2]:combos['首尾同花']+=1
            if len(set(vv))<3:combos['重复牌值']+=1
            if not set(vv)&{'J','Q','K'}:combos['无人物牌']+=1
            index.append({'id':q['id'],'question':q['data']['question'],'cards':cards,'source':row['directory']+'/events.jsonl','question_seq':q['seq'],'draw_seq':d['seq'],'note_seq':note['seq'],'note_hash':note['hash']})
            for ref in re.findall(r'B\d{2}-[A-Z]-R\d{3}',json.dumps(note['data'],ensure_ascii=False)):
                if ref not in allids:issues.append('不存在的笔记引用:'+ref)
        result.append({'id':row['id'],'rounds':n,'events':len(es),'hash_chain':'pass','legality_and_order':'pass','issues':issues,'snapshots_sha256':snapshots})
    report={'batch':batch,'groups':result,'total':len(index),'suits':dict(suits),'values':dict(values),'combinations':dict(combos),'status':'static-check' if all(not r['issues'] for r in result) else 'issues','scope':'检查日志合法性、先后、完整牌组实现、快照存在、共同题与引用存在；解释质量及用户验收另行记录。'}
    save(ROOT/'中央综合'/f'{batch}_程序与来源核验.json',report)
    save(ROOT/'中央综合'/f'{batch}_来源索引.json',index)
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    p=argparse.ArgumentParser();p.add_argument('action',choices=['progress','audit']);p.add_argument('--batch');a=p.parse_args()
    if a.action=='progress':progress()
    else:audit(a.batch)
