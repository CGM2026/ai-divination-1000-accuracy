"""Small fictional fixtures only; never part of the formal 1000 cases."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from cardlab import engine as e


class EvaluationTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='fixture_excluded_', dir=Path(__file__).parent)
        self.base = Path(self.temporary.name)
        self.root = self.base / 'run'
        self.stories = self.base / 'stories.json'
        self.skill = self.base / 'skill'
        self.skill.mkdir()
        (self.skill / 'SKILL.md').write_text('TEST FIXTURE ONLY', encoding='utf-8')
        rows = [dict(id=f'F{i+1:03}', domain='fixture', background=f'虚构工具测试题 {i+1}，不属于研究样本。',
                     question='是否按时完成？', deadline='明天 18:00', yes_definition='期限前完成全部事项',
                     outcome=i % 2, ending=f'工具测试结局 {i%2}。', source_type='simulated',
                     source={'reference': 'test fixture', 'evidence': '程序工具测试专用虚构结局'}) for i in range(4)]
        e.save(self.stories, rows)
        e.initialize(self.root, self.stories, self.skill, fixture=True, count=4, batch_size=3)
        e.prepare(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def input(self, name, data):
        path = self.base / name
        e.save(path, data)
        return path

    def predictions(self, arm):
        expected = e.expected_rows(self.root, arm)
        rows = []
        for index, item in enumerate(expected.values()):
            # Explicit artificial outcomes for score arithmetic unit test, not a prediction method.
            pred = [0, 1, 1, 0][index] if arm == 'cards' else [0, 0, 0, 1][index]
            row = dict(id=item['id'], prediction=pred, p_yes=0.8 if pred else 0.2, answer='虚构工具测试回答')
            if arm == 'cards':
                row.update(version='2.0', cards=item['cards'], combined_sentence='工具测试连句',
                           translations=[dict(card=card, suit_meaning='测试花色义', value_meaning='测试牌值义',
                                              context_translation='测试情境译文') for card in item['cards']])
            else:
                row['rationale'] = '工具测试对照说明'
            rows.append(row)
        return rows

    def test_retry_preserves_draws_and_blocks_mutation(self):
        old = {p.name: p.read_bytes() for p in (self.root / 'draws').glob('*.json')}
        e.prepare(self.root)
        self.assertEqual(old, {p.name: p.read_bytes() for p in (self.root / 'draws').glob('*.json')})
        path = next((self.root / 'draws').glob('*.json'))
        path.unlink()
        with self.assertRaisesRegex(ValueError, 'Frozen file changed/missing'):
            e.prepare(self.root)
        self.assertFalse(path.exists(), 'Frozen missing draws must never be redrawn')

    def test_prediction_gate_integrity_and_statistics(self):
        with self.assertRaisesRegex(ValueError, 'Seal ALL'):
            e.score(self.root)
        card_rows = self.predictions('cards')
        bad = copy.deepcopy(card_rows)
        bad[0]['cards'].reverse()
        with self.assertRaisesRegex(ValueError, 'Cards/order changed'):
            e.submit(self.root, 'cards', self.input('bad.json', bad))
        e.submit(self.root, 'cards', self.input('cards.json', card_rows))
        with self.assertRaisesRegex(ValueError, 'need all'):
            e.seal(self.root)
        e.submit(self.root, 'no_cards', self.input('base.json', self.predictions('no_cards')))
        e.seal(self.root)
        with self.assertRaisesRegex(ValueError, 'already sealed'):
            e.submit(self.root, 'cards', self.base / 'cards.json')
        audit = [dict(id=f'F{i+1:03}', status='ambiguous' if i == 0 else 'pass', reason='工具测试审计') for i in range(4)]
        audit[0]['alternative_outcome'] = 1
        e.submit_audit(self.root, self.input('audit.json', audit))
        summary = e.score(self.root)
        self.assertEqual(summary['cards']['correct'], 2)
        self.assertEqual(summary['no_cards']['correct'], 3)
        self.assertAlmostEqual(summary['cards']['brier'], 0.34)
        self.assertEqual(summary['cards_only_correct'], 1)
        self.assertEqual(summary['no_cards_only_correct'], 2)
        self.assertEqual(summary['mcnemar_exact_two_sided'], 1.0)
        result = e.read(self.root / 'results.json')
        self.assertEqual(result['sensitivity']['exclude_nonpass']['cards']['n'], 3)
        self.assertEqual(result['sensitivity']['alternative_labels']['cards']['correct'], 1)
        self.assertEqual(e.verify(self.root)['status'], 'static-check')

    def test_duplicate_story_and_nan_rejected(self):
        rows = e.read(self.stories)
        rows[1]['id'] = rows[0]['id']
        with self.assertRaisesRegex(ValueError, 'Duplicate ID'):
            e.validate_stories(rows, 4)
        pred = self.predictions('cards')[0]
        pred['p_yes'] = float('nan')
        with self.assertRaisesRegex(ValueError, 'finite probability'):
            e.validate_prediction(pred, e.expected_rows(self.root, 'cards'), 'cards')


if __name__ == '__main__':
    unittest.main()
