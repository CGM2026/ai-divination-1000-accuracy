"""Standard-library frozen evaluation. Never generates forecast text or outcomes."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import re
import shutil
import sys

VERSION = '2.0'
SUITS = ['红桃', '方块', '梅花', '黑桃']
VALUES = ['A'] + [str(n) for n in range(2, 11)] + ['J', 'Q', 'K']
DECK = [s + v for s in SUITS for v in VALUES]
PUBLIC_FIELDS = ['id', 'domain', 'background', 'question', 'deadline', 'yes_definition']


def require(ok, message):
    if not ok:
        raise ValueError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    """Exclusive creation prevents silently rewriting any frozen record."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def text_field(row, key):
    require(isinstance(row.get(key), str) and bool(row[key].strip()),
            f"{row.get('id', '?')}: {key} must be nonempty text")


def validate_stories(rows, count):
    require(isinstance(rows, list) and len(rows) == count, f'Expected {count} stories')
    ids, fingerprints = set(), set()
    for row in rows:
        require(isinstance(row, dict), 'Story must be an object')
        for field in PUBLIC_FIELDS + ['ending', 'source_type']:
            text_field(row, field)
        require(re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{1,63}', row['id']), 'Unsafe story ID')
        require(row['id'] not in ids, f"Duplicate ID: {row['id']}")
        ids.add(row['id'])
        fp = (row['background'].strip(), row['question'].strip())
        require(fp not in fingerprints, f"Duplicate question/background: {row['id']}")
        fingerprints.add(fp)
        require(type(row.get('outcome')) is int and row['outcome'] in [0, 1], 'Outcome must be 0 or 1')
        require(row['source_type'] in ['real', 'simulated'], 'source_type must be real or simulated')
        require(isinstance(row.get('source'), dict), 'source must be an object')
        for field in ['reference', 'evidence']:
            text_field(row['source'], field)
    return rows


def manifest(root, paths):
    return {p.relative_to(root).as_posix(): digest(p) for p in sorted(paths)}


def verify_manifest(root, record):
    for name, expected in record['files'].items():
        path = root / name
        require(path.is_file() and digest(path) == expected, f'Frozen file changed/missing: {name}')


def validate_init(root):
    frozen = read(root / 'freezes/initial.json')
    verify_manifest(root, frozen)
    config = read(root / 'config.json')
    require(config['version'] == VERSION, 'Unexpected method version')
    return config


def initialize(root, stories, skill, fixture=False, count=1000, batch_size=25):
    require(not root.exists() or not any(root.iterdir()), 'Run directory must be empty')
    require(fixture or count == 1000, 'Formal evaluation requires exactly 1000 cases')
    require(count > 0 and batch_size > 0, 'Count and batch size must be positive')
    rows = validate_stories(read(stories), count)
    skill = Path(skill)
    require((skill / 'SKILL.md').is_file(), 'Skill directory must contain SKILL.md')
    save(root / 'private/stories.json', rows)
    public = [{key: row[key] for key in PUBLIC_FIELDS} for row in rows]
    save(root / 'public/questions.json', public)
    save(root / 'config.json', {'version': VERSION, 'count': count, 'batch_size': batch_size,
         'fixture': fixture, 'created_at': now(), 'source_counts': dict(Counter(x['source_type'] for x in rows)),
         'question_order': [x['id'] for x in rows], 'threshold': 0.5,
         'protocol': 'All predictions frozen before any scoring; no within-test tuning.'})
    shutil.copytree(skill, root / 'method', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    paths = [p for p in root.rglob('*') if p.is_file()]
    save(root / 'freezes/initial.json', {'created_at': now(), 'files': manifest(root, paths)})
    return {'initialized': count, 'fixture': fixture}


def prepare(root):
    config = validate_init(root)
    freeze_path = root / 'freezes/draws_packets.json'
    if freeze_path.exists():
        verify_manifest(root, read(freeze_path))
    public = read(root / 'public/questions.json')
    frozen_at = read(root / 'freezes/initial.json')['created_at']
    card_rows = []
    for row in public:
        path = root / 'draws' / (row['id'] + '.json')
        public_hash = hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if path.exists():
            draw = read(path)
            require(draw['input_sha256'] == public_hash, 'Draw input changed')
        else:
            draw = {'id': row['id'], 'created_at': now(), 'input_sha256': public_hash,
                    'cards': random.SystemRandom().sample(DECK, 3)}
            save(path, draw)
        require(draw['created_at'] >= frozen_at, 'Draw precedes story freeze')
        require(len(draw['cards']) == 3 and len(set(draw['cards'])) == 3 and set(draw['cards']) <= set(DECK),
                'Invalid draw')
        card_rows.append(dict(row, cards=draw['cards'], version=VERSION))
    size = config['batch_size']
    for start in range(0, len(public), size):
        end = min(start + size, len(public))
        name = f'{start+1:04}-{end:04}.json'
        for arm, rows in [('cards', card_rows), ('no_cards', public)]:
            path = root / 'packets' / arm / name
            payload = rows[start:end]
            if path.exists():
                require(read(path) == payload, 'Existing packet changed')
            else:
                save(path, payload)
    if freeze_path.exists():
        verify_manifest(root, read(freeze_path))
    else:
        paths = [p for folder in ['draws', 'packets'] for p in (root / folder).rglob('*.json')]
        save(freeze_path, {'created_at': now(), 'files': manifest(root, paths)})
    return {'draws': len(card_rows), 'packets_per_arm': math.ceil(len(public) / size)}


def expected_rows(root, arm):
    require(arm in ['cards', 'no_cards'], 'Unknown prediction arm')
    verify_manifest(root, read(root / 'freezes/draws_packets.json'))
    return {row['id']: row for path in sorted((root / 'packets' / arm).glob('*.json')) for row in read(path)}


def validate_prediction(row, expected, arm):
    require(isinstance(row, dict) and row.get('id') in expected, 'Unknown prediction ID')
    require(type(row.get('prediction')) is int and row['prediction'] in [0, 1], 'prediction must be 0 or 1')
    probability = row.get('p_yes')
    require(type(probability) in [int, float] and math.isfinite(probability) and 0 <= probability <= 1,
            'p_yes must be a finite probability')
    require(row['prediction'] == int(probability >= 0.5), 'Prediction/probability disagree')
    text_field(row, 'answer')
    require(not set(row) & {'outcome', 'ending', 'correct', 'feedback'}, 'Prediction contains outcome fields')
    if arm == 'cards':
        require(row.get('version') == VERSION, 'Wrong method version')
        require(row.get('cards') == expected[row['id']]['cards'], 'Cards/order changed')
        require(isinstance(row.get('translations'), list) and len(row['translations']) == 3,
                'Need three card translations')
        for card, translation in zip(row['cards'], row['translations']):
            require(translation.get('card') == card, 'Translation card/order mismatch')
            for key in ['suit_meaning', 'value_meaning', 'context_translation']:
                text_field(translation, key)
        text_field(row, 'combined_sentence')
    else:
        text_field(row, 'rationale')
        require(not set(row) & {'cards', 'translations', 'combined_sentence'}, 'No-card arm contains cards')


def submit(root, arm, input_path):
    validate_init(root)
    require(not (root / 'freezes/all_predictions.json').exists(), 'Prediction phase already sealed')
    expected = expected_rows(root, arm)
    rows = read(input_path)
    require(isinstance(rows, list) and bool(rows), 'Submit a nonempty JSON array')
    require(len({row.get('id') for row in rows}) == len(rows), 'Duplicate prediction IDs')
    for row in rows:
        validate_prediction(row, expected, arm)
        path = root / 'predictions' / arm / (row['id'] + '.json')
        require(not path.exists() or read(path) == row, 'Existing prediction cannot be replaced')
    for row in rows:
        path = root / 'predictions' / arm / (row['id'] + '.json')
        freeze = root / 'freezes/submissions' / arm / (row['id'] + '.json')
        if not path.exists():
            save(path, row)
        if not freeze.exists():
            save(freeze, {'created_at': now(), 'files': manifest(root, [path])})
        verify_manifest(root, read(freeze))
    return {'arm': arm, 'submitted': len(rows), 'total': len(list((root / 'predictions' / arm).glob('*.json')))}


def validate_all_predictions(root):
    config = validate_init(root)
    paths = []
    for arm in ['cards', 'no_cards']:
        expected = expected_rows(root, arm)
        predictions = list((root / 'predictions' / arm).glob('*.json'))
        require(len(predictions) == config['count'], f'{arm}: need all {config["count"]} predictions before reveal')
        ids = set()
        for path in predictions:
            row = read(path)
            validate_prediction(row, expected, arm)
            require(row['id'] not in ids and path.stem == row['id'], 'Duplicate/misnamed prediction')
            ids.add(row['id'])
            verify_manifest(root, read(root / 'freezes/submissions' / arm / path.name))
        require(ids == set(expected), 'Missing prediction IDs')
        paths.extend(predictions)
    return paths


def seal(root):
    paths = validate_all_predictions(root)
    path = root / 'freezes/all_predictions.json'
    if path.exists():
        verify_manifest(root, read(path))
    else:
        save(path, {'created_at': now(), 'files': manifest(root, paths)})
    return {'sealed_predictions': len(paths)}


def submit_audit(root, input_path):
    config = validate_init(root)
    expected = {x['id'] for x in read(root / 'public/questions.json')}
    rows = read(input_path)
    require(isinstance(rows, list) and len(rows) == config['count'], 'Audit must cover every story')
    require({x['id'] for x in rows} == expected, 'Audit IDs do not match stories')
    for row in rows:
        require(row.get('status') in ['pass', 'ambiguous', 'contradictory'], 'Invalid audit status')
        text_field(row, 'reason')
        if 'alternative_outcome' in row:
            require(type(row['alternative_outcome']) is int and row['alternative_outcome'] in [0, 1], 'Invalid alternative label')
    save(root / 'private/outcome_audit.json', rows)
    save(root / 'freezes/audit.json', {'created_at': now(), 'files': manifest(root, [root / 'private/outcome_audit.json'])})
    return dict(Counter(row['status'] for row in rows))


def statistics(rows, arm):
    n = len(rows)
    if not n:
        return {'n': 0, 'correct': 0, 'accuracy': None, 'wilson95': None, 'brier': None}
    correct = sum(row[arm]['prediction'] == row['outcome'] for row in rows)
    p, z = correct / n, 1.959963984540054
    center = (p + z*z/(2*n)) / (1 + z*z/n)
    radius = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / (1 + z*z/n)
    return {'n': n, 'correct': correct, 'accuracy': p, 'wilson95': [center-radius, center+radius],
            'brier': sum((row[arm]['p_yes'] - row['outcome'])**2 for row in rows) / n}


def comparison(rows):
    yes = sum(row['outcome'] for row in rows)
    both_right = both_wrong = cards_only = base_only = 0
    for row in rows:
        c = row['cards_prediction']['prediction'] == row['outcome']
        b = row['no_cards_prediction']['prediction'] == row['outcome']
        both_right += c and b
        both_wrong += not c and not b
        cards_only += c and not b
        base_only += b and not c
    discordant = cards_only + base_only
    p = min(1.0, 2 * (sum(math.comb(discordant, k) for k in range(min(cards_only, base_only)+1)) / 2**discordant)) if discordant else 1.0
    return {'cards': statistics(rows, 'cards_prediction'), 'no_cards': statistics(rows, 'no_cards_prediction'),
            'outcome_yes': yes, 'majority_reference': max(yes, len(rows)-yes)/len(rows) if rows else None,
            'both_correct': both_right, 'both_wrong': both_wrong, 'cards_only_correct': cards_only,
            'no_cards_only_correct': base_only, 'accuracy_difference': (cards_only-base_only)/len(rows) if rows else None,
            'mcnemar_exact_two_sided': p}


def score(root):
    config = validate_init(root)
    require((root / 'freezes/all_predictions.json').exists(), 'Seal ALL predictions in BOTH arms before scoring')
    validate_all_predictions(root)
    verify_manifest(root, read(root / 'freezes/all_predictions.json'))
    verify_manifest(root, read(root / 'freezes/audit.json'))
    audit = {x['id']: x for x in read(root / 'private/outcome_audit.json')}
    rows = []
    for story in read(root / 'private/stories.json'):
        item = dict(story)
        for arm in ['cards', 'no_cards']:
            item[arm + '_prediction'] = read(root / 'predictions' / arm / (story['id'] + '.json'))
        item['audit'] = audit[story['id']]
        item['draw'] = read(root / 'draws' / (story['id'] + '.json'))
        rows.append(item)
    summary = {'all': comparison(rows), 'by_domain': {}, 'by_source_type': {}}
    for field, output in [('domain', 'by_domain'), ('source_type', 'by_source_type')]:
        for value in sorted({row[field] for row in rows}):
            summary[output][value] = comparison([row for row in rows if row[field] == value])
    clean = [row for row in rows if row['audit']['status'] == 'pass']
    alternative = [dict(row, outcome=row['audit'].get('alternative_outcome', row['outcome'])) for row in rows]
    report = {'created_at': now(), 'version': VERSION, 'fixture': config['fixture'], 'summary': summary,
              'audit_counts': dict(Counter(row['audit']['status'] for row in rows)),
              'sensitivity': {'exclude_nonpass': comparison(clean), 'alternative_labels': comparison(alternative),
                              'alternative_label_count': sum('alternative_outcome' in row['audit'] for row in rows)},
              'interpretation': 'Accuracy describes this frozen dataset only. New retrospective readings never replace original forecasts. Theory and story realism are not established by this score. Shared filesystem access is not technical blinding.',
              'rows': rows}
    save(root / 'results.json', report)
    save(root / 'freezes/results.json', {'created_at': now(), 'files': manifest(root, [root / 'results.json'])})
    return summary['all']


def verify(root):
    config = validate_init(root)
    for path in sorted((root / 'freezes').rglob('*.json')):
        verify_manifest(root, read(path))
    draws = list((root / 'draws').glob('*.json'))
    if (root / 'freezes/all_predictions.json').exists():
        validate_all_predictions(root)
    return {'status': 'static-check', 'fixture': config['fixture'], 'count': config['count'],
            'draws': len(draws), 'results_exist': (root / 'results.json').exists()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    sub = parser.add_subparsers(dest='action', required=True)
    init = sub.add_parser('init')
    init.add_argument('--stories', type=Path, required=True)
    init.add_argument('--skill', type=Path, required=True)
    init.add_argument('--fixture', action='store_true')
    init.add_argument('--count', type=int, default=1000)
    init.add_argument('--batch-size', type=int, default=25)
    for action in ['prepare', 'seal', 'score', 'verify']:
        sub.add_parser(action)
    submit_parser = sub.add_parser('submit')
    submit_parser.add_argument('--arm', choices=['cards', 'no_cards'], required=True)
    submit_parser.add_argument('--input', type=Path, required=True)
    audit_parser = sub.add_parser('audit')
    audit_parser.add_argument('--input', type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.action == 'init':
        result = initialize(root, args.stories, args.skill, args.fixture, args.count, args.batch_size)
    elif args.action == 'submit':
        result = submit(root, args.arm, args.input)
    elif args.action == 'audit':
        result = submit_audit(root, args.input)
    else:
        result = {'prepare': prepare, 'seal': seal, 'score': score, 'verify': verify}[args.action](root)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
