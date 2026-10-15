import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from cardlab import cli as c, engine as e


class PortableTests(unittest.TestCase):
    def test_seed_is_portable_and_demo_scores(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            base = Path(tmp)
            result = c.demo(base / 'demo')
            self.assertEqual(result['external_calls'], 0)
            first = base / 'demo/run'
            second = base / 'second'
            e.initialize(second, base / 'demo/fixture-stories.json',
                         c.REPO / 'methods/evaluation-2.0-frozen',
                         fixture=True, count=4, batch_size=2, seed=42)
            e.prepare(second)
            self.assertEqual(
                {k: r['cards'] for k, r in e.expected_rows(first, 'cards').items()},
                {k: r['cards'] for k, r in e.expected_rows(second, 'cards').items()})

    def test_api_contract_and_metadata_without_credentials(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            cfg = Path(tmp) / 'config.json'
            cfg.write_text(json.dumps({'provider': {'endpoint': 'https://example.invalid/chat',
                'model': 'requested', 'api_key_env': 'CARDLAB_TEST_TOKEN'}, 'roles': {}}))
            response = {'model': 'returned', 'choices': [{'message': {'content': '```json\n[{"id":"N1"}]\n```'}}]}
            with patch.dict(c.os.environ, {'CARDLAB_TEST_TOKEN': 'test-only-value'}), patch.object(
                    c, 'urlopen', return_value=io.StringIO(json.dumps(response))) as call:
                data, metadata = c.model_call(cfg, 'cards', 'system', 'public input')
                payload = json.loads(call.call_args.args[0].data)
            self.assertEqual(data, [{'id': 'N1'}])
            self.assertEqual(payload['messages'][1]['content'], 'public input')
            self.assertEqual(metadata['returned_model'], 'returned')
            self.assertNotIn('test-only-value', json.dumps(metadata))

    def test_predictor_receives_only_its_packet_and_method(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            base = Path(tmp)
            c.demo(base / 'demo')
            run = base / 'demo/run'
            for arm in ['cards', 'no_cards']:
                packet = next((run / 'packets' / arm).glob('*.json'))
                batch = c.read(packet)
                rows = []
                for r in batch:
                    p = dict(id=r['id'], prediction=0, p_yes=.2, answer='固定测试')
                    if arm == 'cards':
                        p.update(version='2.0', cards=r['cards'], combined_sentence='固定测试',
                            translations=[dict(card=x, suit_meaning='测试', value_meaning='测试',
                                               context_translation='测试') for x in r['cards']])
                    else:
                        p['rationale'] = '固定测试'
                    rows.append(p)
                args = c.parser().parse_args(['predict', '--root', str(run), '--packet', str(packet),
                    '--arm', arm, '--config', 'unused', '--output', str(base / f'{arm}.json')])
                with patch.object(c, 'model_call', return_value=(rows, {'mock': True})) as call:
                    c.predict(args)
                sent = json.loads(call.call_args.args[3])
                self.assertEqual(sent, batch)
                self.assertTrue(all('ending' not in r and 'outcome' not in r for r in sent))
                self.assertEqual('cards' in sent[0], arm == 'cards')
                if arm == 'no_cards':
                    self.assertNotIn('黑桃', call.call_args.args[2])

    def test_archive_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            memory = io.BytesIO()
            with zipfile.ZipFile(memory, 'w') as z:
                z.writestr('../escape.txt', 'bad')
            memory.seek(0)
            with zipfile.ZipFile(memory) as z, self.assertRaisesRegex(ValueError, 'Unsafe'):
                c.safe_extract(z, tmp)

    def test_whole_dataset_statistics(self):
        result = e.comparison(c.records('evaluation-1000'))
        self.assertEqual((result['cards']['correct'], result['no_cards']['correct']), (704, 691))
        self.assertAlmostEqual(result['mcnemar_exact_two_sided'], .213153, places=6)


if __name__ == '__main__':
    unittest.main()
