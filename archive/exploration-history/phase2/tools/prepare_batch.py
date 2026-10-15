"""Create task folders only from an approved central batch configuration."""
from pathlib import Path
import argparse,json
ROOT=Path(__file__).resolve().parents[1]
def write(p,text):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8')
def save(p,obj):write(p,json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
def main(batch):
    base=ROOT/'批次'/batch
    config=json.loads((base/'批次配置.json').read_text(encoding='utf-8'))
    if not (base/'计划与选题理由.md').exists():raise ValueError('先写批次选择与接续依据')
    protocol=(ROOT/'工具/研究者协议.md').read_text(encoding='utf-8')
    rows=json.loads((ROOT/'研究对话登记.json').read_text(encoding='utf-8-sig'))
    handoff=(ROOT/config['handoff']).read_text(encoding='utf-8')
    for group in config['groups']:
        prefix=batch+'-'+group['group'];folder=base/group['group'];rel=folder.relative_to(ROOT).as_posix()
        if any(r['id']==prefix for r in rows):raise ValueError('已登记，不能重复准备')
        (folder/'inputs').mkdir(parents=True,exist_ok=True)
        write(folder/'阶段候选视角.md',handoff)
        if config.get('reread'):
            from draw import read_events
            material=[]
            for rid in config['reread']:
                b,g,rn=rid.split('-'); n=int(rn[1:])
                src=ROOT/'批次'/b/g
                es=[e for e in read_events(src) if e['round']==n]
                material.append({'id':rid,'question':es[0]['data']['question'],'cards':es[1]['data'],'source':src.relative_to(ROOT).as_posix()+'/events.jsonl','draw_seq':es[1]['seq'],'draw_hash':es[1]['hash']})
            save(folder/'重读材料.json',material)
        if config.get('common'):save(folder/'共同场景.json',config['common'])
        task=f'''# {prefix}：{group['title']}

你的记录目录：{folder.as_posix()}
共享工具：{(ROOT/'工具/draw.py').as_posix()}
模型请求：gpt-6.1-sol，thinking=medium。

{protocol}

## 本批接续
你可读取自己目录的阶段候选视角.md。这些是前批可使用、扩展或另读的候选视角，保留自己的语言。不要读取同批其他组目录。

## 本组任务
{group['task']}

{config.get('shared_task','')}

{('自己目录共同场景.json所列轮次必须逐字使用对应question，其余轮次按上述目标提出具体问题。' if config.get('common') else '每8轮在本组主题内更换一类日常情境，保持有具体事实的追问。')}

工具调用格式：python "{(ROOT/'工具/draw.py').as_posix()}" --dir "{folder.as_posix()}" --prefix {prefix} question --round 1 --input "{(folder/'inputs/q001.json').as_posix()}"。
随后draw --round 1，实际看到返回后才写笔记并note --round 1 --input 笔记路径。每8轮snapshot --round 8 --input 快照草稿；最终render。只使用共享工具。按24轮完成所有记录与快照、研究小结、进度.json，再回复。
'''
        write(folder/'任务提示词.md',task)
        rows.append(dict(id=prefix,title=group['title'],prompt=rel+'/任务提示词.md',directory=rel,model='gpt-6.1-sol',thinking='medium',thread_id=None,status='prepared',completed=0,target=24,cursor=None))
    save(ROOT/'研究对话登记.json',rows)
    state=json.loads((ROOT/'实验状态.json').read_text(encoding='utf-8'));state.update(batch=batch,next=f'创建并完成{batch}各组，核验原始记录与快照后综合，依据实际发现安排后续')
    save(ROOT/'实验状态.json',state)
    print(batch+' prepared')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('batch');main(p.parse_args().batch)
