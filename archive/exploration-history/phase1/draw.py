"""Sequential, question-first random card dialogue recorder. Python stdlib only."""
import argparse
import json
import os
import random
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GROUPS = ('01_body', '02_relation', '03_time')
RANKS = ['A'] + [str(i) for i in range(2, 11)] + ['J', 'Q', 'K']
SUITS = ['H', 'D', 'C', 'S']
GLYPHS = dict(H='♥', D='♦', C='♣', S='♠')
DECK = [s + r for s in SUITS for r in RANKS]

def read_events(folder):
    path = folder / 'events.jsonl'
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line] if path.exists() else []

def append(folder, event):
    event['utc'] = datetime.now(timezone.utc).isoformat()
    with (folder / 'events.jsonl').open('a', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(event, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())

def view(cards):
    return '、'.join(GLYPHS[c[0]] + c[1:] for c in cards)

def validate(events):
    state, n = 'question', 1
    for event in events:
        assert event['type'] == state and event['round'] == n, ('event order', n, state)
        if state == 'question':
            assert event['text'].strip()
            state = 'cards'
        elif state == 'cards':
            assert len(event['cards']) == 3 and len(set(event['cards'])) == 3
            assert all(c in DECK for c in event['cards'])
            state = 'note'
        else:
            assert event['text'].strip()
            state, n = 'question', n + 1
    return state, n

def export(folder, events):
    state, n = validate(events)
    cards = [e for e in events if e['type'] == 'cards']
    counts = Counter(c for e in cards for c in e['cards'])
    stats = {'rounds': len(cards), 'notes': sum(e['type'] == 'note' for e in events),
             'next_state': state, 'next_round': n,
             'suits': {s: sum(v for c, v in counts.items() if c[0] == s) for s in SUITS},
             'ranks': {r: sum(v for c, v in counts.items() if c[1:] == r) for r in RANKS},
             'cards': {c: counts[c] for c in DECK}}
    (folder / 'stats.json').write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# 扑克牌陌生语言逐轮记录', '', 'H=♥；D=♦；C=♣；S=♠。牌顺序为实际抽出顺序。', '']
    for e in events:
        if e['type'] == 'question':
            lines += [f"## 第{e['round']:03d}轮", '', '研究者：' + e['text'], '']
        elif e['type'] == 'cards':
            lines += ['扑克牌回应：' + view(e['cards']), '']
        else:
            lines += ['私下笔记：' + e['text'], '']
    (folder / 'transcript.md').write_text('\n'.join(lines), encoding='utf-8')
    return stats

def main():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['step', 'finish', 'status', 'export'])
    p.add_argument('--group', required=True, choices=GROUPS)
    p.add_argument('--input', type=Path)
    args = p.parse_args()
    folder = ROOT / args.group
    folder.mkdir(exist_ok=True)
    events = read_events(folder)
    state, n = validate(events)
    if args.action in ('status', 'export'):
        print(json.dumps(export(folder, events), ensure_ascii=False))
        return
    req = json.loads(args.input.read_text(encoding='utf-8-sig'))
    if args.action == 'step':
        target = n + (state == 'note')
        assert req['round'] == target and target <= 156
        assert isinstance(req['question'], str) and req['question'].strip()
        if state == 'note':
            assert req.get('previous_note', '').strip(), 'Record previous response before next draw'
            append(folder, {'type': 'note', 'round': n, 'text': req['previous_note']})
        else:
            assert state == 'question', 'Interrupted after committed question: recover, do not redraw'
        append(folder, {'type': 'question', 'round': target, 'text': req['question']})
        selected = random.SystemRandom().sample(DECK, 3)
        append(folder, {'type': 'cards', 'round': target, 'cards': selected})
        print(json.dumps({'round': target, 'cards': selected, 'display': view(selected)}, ensure_ascii=False))
    else:
        assert n == 156 and state == 'note', 'Finish only after 156 actual draws'
        assert req.get('previous_note', '').strip()
        append(folder, {'type': 'note', 'round': n, 'text': req['previous_note']})
        print(json.dumps(export(folder, read_events(folder)), ensure_ascii=False))

if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    main()
