"""Convert fixed XAML presentation values into reversible runtime resources."""
import json
from pathlib import Path
import re
root=Path(__file__).resolve().parents[1]/'src/XAUPY.Desktop'
catalog_path=root/'Assets/appearance-tokens.json'
catalog=json.loads(catalog_path.read_text()) if catalog_path.exists() else dict(colors=[],fonts=[])
colors=set(catalog['colors']);fonts=set(catalog['fonts'])
for path in root.glob('*.axaml'):
    source=path.read_text(encoding='utf-8')
    def color(match):
        attribute,value=match.groups();value=value.upper();colors.add(value)
        kind='Color' if attribute=='Color' else 'Brush'
        return f'{attribute}="{{DynamicResource {kind}_{value[1:]}}}"'
    source=re.sub(r'(Background|Foreground|BorderBrush|Fill|Stroke|Tint|Color|CaretBrush|SelectionBrush)="(#[0-9A-Fa-f]{6,8})"',color,source)
    def setter(match):
        before,value,after=match.groups();value=value.upper();colors.add(value)
        return before+'{DynamicResource Brush_'+value[1:]+'}'+after
    source=re.sub(r'(<Setter Property="(?:Background|Foreground|BorderBrush|Fill|Stroke)" Value=")(#[0-9A-Fa-f]{6,8})("\s*/>)',setter,source)
    def font(match):
        before,value,after=match.groups();fonts.add(float(value))
        return before+'{DynamicResource Font_'+value.replace('.','_')+'}'+after
    source=re.sub(r'(FontSize=")(\d+(?:\.\d+)?)(")',font,source)
    source=re.sub(r'(<Setter Property="FontSize" Value=")(\d+(?:\.\d+)?)("\s*/>)',font,source)
    path.write_text(source,encoding='utf-8')
catalog_path.parent.mkdir(exist_ok=True)
catalog_path.write_text(json.dumps(dict(colors=sorted(colors),fonts=sorted(fonts)),indent=2),encoding='utf-8')
print(len(colors),'color tokens;',len(fonts),'font sizes')
