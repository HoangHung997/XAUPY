"""Resolve actual Vietnamese resources for reference-layout source checks."""
import html
import json
from pathlib import Path
import re

def read_xaml(path):
    resources=Path(__file__).resolve().parents[2]/'src/XAUPY.Desktop/Assets/localization.json'
    catalog=json.loads(resources.read_text(encoding='utf-8'))
    text=path.read_text(encoding='utf-8')
    def resolve(match):
        if match[1] not in catalog:raise AssertionError('Unresolved text resource '+match[1])
        return html.escape(catalog[match[1]]['vi'],quote=True)
    return re.sub(r'\{(?:DynamicResource Text_|local:InitialText )([a-z0-9]+)\}',resolve,text)
