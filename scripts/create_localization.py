"""Bind reviewed catalog entries to XAML and code labels; safe to run repeatedly.

Add translations to Assets/localization.json before running this migration.
Keys are the first 16 hex characters of SHA256 of the Vietnamese source text.
This never translates user data or messages received from the broker.
"""
from pathlib import Path
import hashlib
import html
import json
import re

ROOT = Path(__file__).resolve().parents[1]
folder = ROOT / 'src/XAUPY.Desktop'
catalog = json.loads((folder / 'Assets/localization.json').read_text(encoding='utf-8'))
translations = {row['vi']: row['en'] for row in catalog.values()}
for key, row in catalog.items():
    assert key == hashlib.sha256(row['vi'].encode()).hexdigest()[:16], key
    assert row['en'].strip(), key
for path in folder.glob('*.axaml'):
    original = path.read_text(encoding='utf-8')
    def substitute(match):
        value = html.unescape(match[2])
        if value not in translations:
            return match[0]
        key = hashlib.sha256(value.encode()).hexdigest()[:16]
        return match[1] + '"{DynamicResource Text_' + key + '}"'
    text = re.sub(r'((?:Text|Content|ToolTip\.Tip|PlaceholderText|Title|Header)=)"([^"]*)"', substitute, original)
    if text != original:
        path.write_text(text, encoding='utf-8')
for path in folder.glob('*.cs'):
    original = path.read_text(encoding='utf-8')
    def code_label(match):
        value = match[2].replace(r'\n', '\n').replace(r'\"', '"')
        if value not in translations:
            return match[0]
        return '[LocalizationService.TextProperty] = "' + match[2] + '"'
    # Only object initializer labels; excludes .Text assignments and expressions.
    text = re.sub(r'(?<![.\w])\b(Text|Content)\s*=\s*"((?:[^"\\]|\\.)*)"(?=\s*[,}])', code_label, original)
    if text != original:
        path.write_text(text, encoding='utf-8')
print(f'Validated {len(catalog)} reviewed translations and updated static labels')
