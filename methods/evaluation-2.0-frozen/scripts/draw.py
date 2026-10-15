"""52张牌无放回抽三张；独占创建输出，重复调用保留原抽牌。"""
import argparse
import hashlib
import json
import random
from pathlib import Path
from datetime import datetime, timezone

def draw(source, target):
    raw = Path(source).read_bytes()
    context = json.loads(raw.decode('utf-8-sig'))
    if not context.get('background') or not context.get('question'):
        raise ValueError('输入必须包含 background 和 question')
    digest = hashlib.sha256(raw).hexdigest()
    target = Path(target)
    if target.exists():
        saved = json.loads(target.read_text(encoding='utf-8'))
        if saved['input_sha256'] != digest:
            raise ValueError('此输出已用于不同输入；不能覆盖原抽牌')
        return saved
    deck = [s + v for s in ['红桃','方块','梅花','黑桃'] for v in ['A','2','3','4','5','6','7','8','9','10','J','Q','K']]
    result = dict(created_at=datetime.now(timezone.utc).isoformat(), input_sha256=digest,
                  context=context, cards=random.SystemRandom().sample(deck,3), method='SystemRandom.sample(52,3)', version='1.0')
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open('x', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    except FileExistsError:
        return draw(source, target)
    return result

if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    p=argparse.ArgumentParser()
    p.add_argument('--input',required=True)
    p.add_argument('--output',required=True)
    a=p.parse_args()
    print(json.dumps(draw(a.input,a.output),ensure_ascii=False,indent=2))
