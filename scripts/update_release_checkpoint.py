"""Render current acceptance evidence without changing any per-feature status."""
from pathlib import Path
import csv
import html
from collections import Counter

root=Path(__file__).resolve().parents[1]
with (root/'docs/RELEASE_V1_FEATURE_MATRIX.csv').open(encoding='utf-8-sig',newline='') as stream:
    rows=list(csv.DictReader(stream))
assert len(rows)==172 and len({r['id'] for r in rows})==172
counts=Counter(r['release_status'] for r in rows)
labels={
'IMPLEMENTED_LOCAL_VERIFIED':'Đã kiểm cách ly',
'IMPLEMENTED_LIVE_DATA_VERIFIED':'Đã kiểm dữ liệu MT5 thật',
'IMPLEMENTED_LOCAL_ACCEPTANCE_PENDING':'Còn nghiệm thu gói / giao diện',
'IMPLEMENTED_BROKER_ACCEPTANCE_PENDING':'Còn nghiệm thu hành động broker',
'IMPLEMENTED_RESEARCH_VERIFIED':'Đã kiểm nghiên cứu lịch sử',
'IMPLEMENTED_REPLAY_VERIFIED':'Đã kiểm replay tick',
'IMPLEMENTED_NATIVE_EXPORT_VERIFIED':'Đã xuất native; còn kiểm bản sửa cuối',
'IMPLEMENTED_NATIVE_VERIFIED':'Đã kiểm thao tác native',
'IMPLEMENTED_WINDOWS_LOGON_PENDING':'Còn kiểm đăng nhập Windows',
}
E=html.escape
out=['''<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>XAUPY 1.0 — nghiệm thu 172 chức năng</title><style>
:root{color-scheme:dark}body{font:15px/1.5 system-ui;background:#061827;color:#d9ebfa;margin:0;padding:32px}main{max-width:1500px;margin:auto}h1{font-size:30px;margin-bottom:8px}p{max-width:1100px}a{color:#61bcff}.notice{border-left:4px solid #eaba4d;background:#243021;padding:14px 18px}.cards{display:flex;flex-wrap:wrap;gap:10px;margin:22px 0}.card{border:1px solid #2a4b61;background:#0b2539;padding:12px;min-width:180px;border-radius:8px}.card b{font-size:25px;display:block}input,select,button{font:inherit;background:#0f2b41;color:inherit;border:1px solid #42627a;padding:10px;border-radius:6px;margin:0 8px 15px 0}input{min-width:320px}table{border-collapse:collapse;width:100%;background:#0a2031}th,td{padding:12px;border:1px solid #28475d;vertical-align:top;text-align:left}th{background:#153a54;position:sticky;top:0}.id{white-space:nowrap}.status{color:#91d2ff}.pending{color:#ffd478}.evidence{font-size:12px;overflow-wrap:anywhere;max-width:260px}tr[hidden]{display:none}.muted{color:#a1b8ca}summary{cursor:pointer;color:#76c9fc}@media(max-width:800px){body{padding:14px}table{font-size:12px}th,td{padding:6px}input{min-width:210px}}</style><main>
<h1>XAUPY 1.0 · Nghiệm thu 172 chức năng</h1>
<p class="notice">Đang nghiệm thu — chưa chứng nhận bản phát hành chuẩn hoặc UI giống 100%. Các trạng thái bên dưới phân biệt mã đã kiểm cách ly với dữ liệu MT5, thao tác native và hành động broker. Không dùng kết quả backtest làm bằng chứng đã khớp lệnh.</p>
<p><a href="RELEASE_V1_COMPLETION.md">Nhật ký hoàn thiện</a> · <a href="RESEARCH_20260928.md">Nghiên cứu 9,9 triệu tick</a> · <a href="RELEASE_V1_FEATURE_MATRIX.csv">Tải ma trận CSV</a> · <a href="FEATURE_FUNCTION_AUDIT_20260928.html">Báo cáo trước sửa</a></p>
<p>466 kiểm tra Python · 151 giao tiếp · 123 tương tác Desktop · 18/18 dịch vụ dữ liệu live. Gói được build lại sau mỗi sửa chức năng; phải đối chiếu phiên bản trong bằng chứng.</p>
<div class="cards">''']
for status,count in counts.items():out.append(f'<div class="card"><b>{count}</b>{E(labels[status])}</div>')
out.append('</div><input id="search" placeholder="Tìm chức năng, tab hoặc mã UI…"><select id="state"><option value="">Tất cả trạng thái</option>')
for key,label in labels.items():out.append(f'<option value="{E(key)}">{E(label)}</option>')
out.append('</select><span id="count"></span><table><thead><tr><th>Mục</th><th>Chức năng</th><th>Hiện tại</th><th>Kiểm chứng và giới hạn</th></tr></thead><tbody>')
for r in rows:
 status=r['release_status'];pending='PENDING' in status
 out.append(f'<tr data-status="{E(status)}"><td class="id">{E(r["id"])}<br><span class="muted">{E(r["tab"])}</span></td><td>{E(r["function"])}<br><small class="muted">Trước sửa: {E(r["baseline"])}</small></td><td class="status {"pending" if pending else ""}">{E(labels[status])}</td><td>{E(r["acceptance"])}<details><summary>Bằng chứng</summary><div class="evidence">{E(r["evidence"])}</div></details></td></tr>')
out.append('''</tbody></table><p class="muted">Ma trận là hồ sơ nghiệm thu có phạm vi. Quyền một lệnh DEMO cũ đã dùng; các kiểm broker mới cần một phiên được người dùng cho phép riêng. Không tự đăng xuất Windows hoặc tác động EA khác.</p></main><script>
const q=document.querySelector('#search'),s=document.querySelector('#state'),rs=[...document.querySelectorAll('tbody tr')];function filter(){let n=0;for(const r of rs){r.hidden=!(r.textContent.toLocaleLowerCase('vi').includes(q.value.toLocaleLowerCase('vi'))&&(!s.value||r.dataset.status===s.value));if(!r.hidden)n++;}document.querySelector('#count').textContent=n+' / '+rs.length+' mục';}q.addEventListener('input',filter);s.addEventListener('change',filter);filter();</script></html>''')
path=root/'docs/RELEASE_V1_ACCEPTANCE.html';path.write_text(''.join(out),encoding='utf-8')
print(path)
