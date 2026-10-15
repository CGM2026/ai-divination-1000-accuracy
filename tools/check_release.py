"""Offline delivery checks. No network and no credential values in output."""
from pathlib import Path
import json
import re
import sys
from urllib.parse import unquote, urlsplit
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from cardlab.cli import verify_package

TEXT = {'.md', '.py', '.json', '.jsonl', '.yml', '.yaml', '.txt'}
PATTERNS = {
    'absolute-windows-path': re.compile(r'(?<![A-Za-z])[A-Za-z]:[/\\]'),
    'private-key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'token-shaped-value': re.compile(r'\b(?:ghp_|github_pat_|sk-)[A-Za-z0-9_\-]{20,}'),
}


def check():
    result = verify_package()
    issues = []
    links = 0
    files = json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))['files']
    for name in files:
        path = ROOT / name
        if path.suffix not in TEXT:
            continue
        content = path.read_text(encoding='utf-8-sig')
        for label, pattern in PATTERNS.items():
            if pattern.search(content):
                issues.append({'file': name, 'issue': label})
        if path.suffix == '.md':
            for raw in re.findall(r'\[[^\]]*\]\(([^)]+)\)', content):
                ref = raw.strip().strip('<>')
                if urlsplit(ref).scheme or ref.startswith('#'):
                    continue
                target = unquote(ref.split('#')[0])
                if target and not (path.parent / target).exists():
                    issues.append({'file': name, 'issue': 'broken-local-link', 'target': target})
                links += 1
    with zipfile.ZipFile(ROOT / 'archive/evaluation-1000-frozen.zip') as z:
        archive_texts = 0
        for item in z.infolist():
            if Path(item.filename).suffix not in TEXT:
                continue
            content = z.read(item).decode('utf-8-sig')
            archive_texts += 1
            for label, pattern in PATTERNS.items():
                if pattern.search(content):
                    issues.append({'file': 'archive/' + item.filename, 'issue': label})
    result.update(local_links_checked=links, archive_text_files_checked=archive_texts, issues=issues)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return bool(issues)


if __name__ == '__main__':
    raise SystemExit(check())
