"""Append-only, question-before-draw research protocol. Python stdlib only."""
from question_wording import display_question
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import sys
from datetime import datetime, timezone
from contextlib import contextmanager

SUITS = ['梅花', '方块', '红桃', '黑桃']
VALUES = ['A'] + [str(n) for n in range(2, 11)] + ['J', 'Q', 'K']
DECK = [s + v for s in SUITS for v in VALUES]

def digest(x):
    return hashlib.sha256(json.dumps(x, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()

@contextmanager
def lock(folder):
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / '.lock').open('a+b') as f:
        f.seek(0)
        if os.name == 'nt':
            import msvcrt
            if f.read(1) == b'':
                f.write(b'0'); f.flush()
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            f.seek(0)
            if os.name == 'nt':
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

def read_events(folder):
    p = folder / 'events.jsonl'
    if not p.exists():
        return []
    raw = p.read_bytes()
    if raw and not raw.endswith(b'\n'):
        raise ValueError('日志末行不完整：保留原文件并联系主持者，不得重新抽牌')
    events = [json.loads(line) for line in raw.decode('utf-8').splitlines()]
    previous = '0' * 64
    round_no, phase = 1, 'question'
    for i, e in enumerate(events, 1):
        body = {k: v for k, v in e.items() if k != 'hash'}
        if e['seq'] != i or e['previous'] != previous or e['hash'] != digest(body):
            raise ValueError('日志校验失败，禁止续写')
        if e['round'] != round_no or e['event'] != phase:
            raise ValueError('事件顺序异常')
        if phase == 'draw' and (len(e['data']) != 3 or len(set(e['data'])) != 3 or any(c not in DECK for c in e['data'])):
            raise ValueError('非法牌面')
        if phase == 'question': phase = 'draw'
        elif phase == 'draw': phase = 'note'
        else: round_no, phase = round_no + 1, 'question'
        previous = e['hash']
    return events

def append(folder, events, prefix, n, kind, data):
    e = dict(seq=len(events)+1, id=f'{prefix}-R{n:03d}', round=n, event=kind,
             time=datetime.now(timezone.utc).isoformat(), data=data,
             previous=events[-1]['hash'] if events else '0'*64)
    e['hash'] = digest(e)
    with (folder / 'events.jsonl').open('ab') as f:
        f.write((json.dumps(e, ensure_ascii=False)+'\n').encode('utf-8'))
        f.flush(); os.fsync(f.fileno())
    return e

def operate(folder, prefix, action, n=None, data=None):
    folder = Path(folder)
    with lock(folder):
        events = read_events(folder)
        if events and any(e['id'] != f"{prefix}-R{e['round']:03d}" for e in events):
            raise ValueError('研究编号不一致')
        if action == 'status':
            return {'events':len(events), 'completed':sum(e['event']=='note' for e in events), 'last':events[-1] if events else None}
        if action == 'render':
            lines = [f'# {prefix} 完整记录', '', '提问措辞说明：本记录中的情境解读题，是请解读者用实际抽到的三张扑克牌描述和解释题面所给情境，并回应具体问题。阅读版已将含糊问法改写清楚；原始日志保留当时原文。前360轮的情境解读与后来100例预测未知结局的测试分别理解。', '']
            for e in events:
                if e['event']=='question':
                    lines += [f"## {e['id']}", '', '提问（明确表述）：'+display_question(e['data']['question']), '', '观察目标：'+e['data']['observation'], '']
                elif e['event']=='draw': lines += ['牌序：'+'、'.join(e['data']), '']
                else:
                    lines += [e['data']['natural_reading'], '', '研究栏：', '']
                    for k,v in e['data']['research'].items(): lines += [f'- {k}：{v}']
                    lines += ['']
            (folder/'完整记录.md').write_text('\n'.join(lines), encoding='utf-8')
            return {'rendered':str(folder/'完整记录.md')}
        if action == 'snapshot':
            if not n or n % 8 or len(events) != n*3:
                raise ValueError('快照只能在当前第8/16/24/32轮笔记完成后保存')
            p=folder/f'快照_{n:02d}.md'
            if p.exists():
                if p.read_text(encoding='utf-8') != data: raise ValueError('快照已存在，不可改写；请另存修订')
            else:
                with p.open('x', encoding='utf-8') as f: f.write(data)
            return {'snapshot':str(p)}
        if not n or n < 1: raise ValueError('需要正整数轮次')
        same = [e for e in events if e['round']==n and e['event']==action]
        if same:
            if action != 'draw' and same[0]['data'] != data: raise ValueError('已保存内容不可改写')
            return same[0]['data'] if action=='draw' else {'saved':same[0]['id'], 'recovered':True}
        expected_n=len(events)//3+1
        expected_action=['question','draw','note'][len(events)%3]
        if n != expected_n or action != expected_action:
            raise ValueError(f'当前必须执行第{expected_n}轮 {expected_action}；先检查 status')
        if action=='question':
            if n>1 and (n-1)%8==0 and not (folder/f'快照_{n-1:02d}.md').exists():
                raise ValueError('先保存上八轮快照')
            if not isinstance(data,dict) or not data.get('question') or not data.get('observation'):
                raise ValueError('问题须有 question 与 observation')
        elif action=='draw':
            data=random.SystemRandom().sample(DECK,3)
        elif action=='note':
            if not isinstance(data,dict) or not data.get('natural_reading') or not isinstance(data.get('research'),dict):
                raise ValueError('笔记须有 natural_reading 和 research')
            for key in ['牌面依据','沿用理解','新联想','待观察']:
                if key not in data['research']: raise ValueError('research缺少：'+key)
        else: raise ValueError('未知动作')
        e=append(folder,events,prefix,n,action,data)
        return data if action=='draw' else {'saved':e['id'], 'event':action}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--dir',required=True); p.add_argument('--prefix',required=True)
    p.add_argument('action',choices=['question','draw','note','snapshot','status','render'])
    p.add_argument('--round',type=int); p.add_argument('--input')
    a=p.parse_args()
    data=None
    if a.input:
        raw=Path(a.input).read_text(encoding='utf-8-sig')
        data=raw if a.action=='snapshot' else json.loads(raw)
    result=operate(a.dir,a.prefix,a.action,a.round,data)
    print('、'.join(result) if a.action=='draw' else json.dumps(result,ensure_ascii=False))

if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    try: main()
    except (ValueError,OSError,json.JSONDecodeError) as e:
        print('ERROR: '+str(e),file=sys.stderr); sys.exit(2)
