import argparse
import json
import random
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG = ROOT / 'events.jsonl'

def append(event):
    event['time'] = datetime.now(timezone.utc).isoformat()
    with LOG.open('a', encoding='utf-8') as f:
        f.write(json.dumps(event, ensure_ascii=False) + '\n')

parser = argparse.ArgumentParser()
parser.add_argument('action', choices=['draw', 'note'])
parser.add_argument('round', type=int)
parser.add_argument('file')
args = parser.parse_args()
events = [json.loads(x) for x in LOG.read_text(encoding='utf-8').splitlines()] if LOG.exists() else []
if not 1 <= args.round <= 6:
    raise SystemExit('Only six rounds are authorized.')
if args.action == 'draw':
    if len(events) != (args.round - 1) * 3:
        raise SystemExit('Finish the previous round before drawing; do not redraw.')
    question = Path(args.file).read_text(encoding='utf-8-sig').strip()
    append({'round': args.round, 'type': 'question', 'text': question})
    deck = [s + r for s in ['黑桃', '红桃', '方块', '梅花'] for r in ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']]
    cards = random.SystemRandom().sample(deck, 3)
    append({'round': args.round, 'type': 'cards', 'cards': cards})
    print(json.dumps(cards, ensure_ascii=False))
else:
    if len(events) != (args.round - 1) * 3 + 2 or events[-1]['type'] != 'cards':
        raise SystemExit('Notes require this round’s completed draw.')
    note = Path(args.file).read_text(encoding='utf-8-sig').strip()
    append({'round': args.round, 'type': 'note', 'text': note})
    print('Saved round', args.round)
