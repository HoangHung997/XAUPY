"""Resolve every AXAML Button/MenuItem action against its owning C# partial class.

This is a binding check, NOT functional or broker end-to-end acceptance. Dynamic
controls and their outcomes are covered by the separate interaction/protocol tests.
"""
from pathlib import Path
import argparse
import csv
import json
import re
import xml.etree.ElementTree as ET


def audit(root: Path) -> dict:
    desktop = root / 'src/XAUPY.Desktop'
    catalog = json.loads((desktop / 'Assets/localization.json').read_text(encoding='utf-8'))
    rows, missing, single = [], [], []
    for path in sorted(desktop.glob('*.axaml')):
        document = ET.parse(path)
        owner = document.getroot().get('{http://schemas.microsoft.com/winfx/2006/xaml}Class', '').split('.')[-1]
        sources = {source:source.read_text(encoding='utf-8') for source in desktop.glob(owner+'*.cs')} if owner else {}
        for node in document.iter():
            kind = node.tag.split('}')[-1]
            attributes = node.attrib
            if kind == 'ComboBox' and len([child for child in node if child.tag.split('}')[-1]=='ComboBoxItem']) == 1:
                single.append(dict(file=str(path.relative_to(root)), name=attributes.get('{http://schemas.microsoft.com/winfx/2006/xaml}Name','')))
            if kind not in ('Button','MenuItem'):
                continue
            name=attributes.get('{http://schemas.microsoft.com/winfx/2006/xaml}Name','')
            label=attributes.get('Content',attributes.get('Header',''))
            match=re.fullmatch(r'\{DynamicResource Text_(\w+)\}',label)
            if match:label=catalog.get(match[1],{}).get('vi',label)
            handler=attributes.get('Click','')
            command=attributes.get('Command','')
            definitions=[]
            if handler:
                pattern=re.compile(r'\b(?:void|Task(?:<[^>]+>)?)\s+'+re.escape(handler)+r'\s*\(')
                for source,text in sources.items():
                    for occurrence in pattern.finditer(text):
                        definitions.append(f'{source.relative_to(root)}:{text[:occurrence.start()].count(chr(10))+1}')
            resolved=bool(command or definitions)
            row=dict(file=str(path.relative_to(root)),owner=owner,control=kind,name=name,label=label,
                     handler=handler or command,definitions='; '.join(definitions),binding_resolved=resolved)
            rows.append(row)
            if not resolved:missing.append(row)
    return dict(scope='AXAML_ACTION_BINDINGS_ONLY; NOT FUNCTIONAL_OR_BROKER_E2E_PROOF',
                controls=len(rows),resolved=len(rows)-len(missing),missing=missing,
                one_option_selectors=single,actions=rows)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('artifacts/rc2-ui-audit/action-bindings.json'))
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    report=audit(root)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    with args.output.with_suffix('.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(report['actions'][0]))
        writer.writeheader();writer.writerows(report['actions'])
    print(f"UI action bindings: {report['resolved']}/{report['controls']}; one-option selectors: {len(report['one_option_selectors'])}; NOT E2E proof")
    if report['missing']:raise SystemExit('Unresolved AXAML action binding')


if __name__=='__main__':main()
