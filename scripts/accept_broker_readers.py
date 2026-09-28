"""Read current MT5 history/native logs into isolated acceptance artifacts."""
import json
import argparse
from pathlib import Path
from xaupy_engine.broker_history import collect
from xaupy_engine.journal import StructuredJournal
from xaupy_engine.mt5_logs import Mt5LogReader

parser=argparse.ArgumentParser()
parser.add_argument('--terminal',required=True);parser.add_argument('--terminal-data',required=True)
parser.add_argument('--login',type=int,required=True);parser.add_argument('--server',required=True)
parser.add_argument('--symbol',required=True);parser.add_argument('--magic',type=int,required=True)
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]/'artifacts/release-v1-reader-acceptance'
root.mkdir(parents=True,exist_ok=True)
(root/'broker').mkdir(exist_ok=True)
identity=dict(account_login=args.login,account_server=args.server,symbol=args.symbol,magic=args.magic)
collect(args.terminal,root/'broker',identity)
reader=Mt5LogReader(root,StructuredJournal(root/'journal'))
try:
    result=reader.read_once(Path(args.terminal_data))
    (root/'native-log-summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))
finally:reader.close()
