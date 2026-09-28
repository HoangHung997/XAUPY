using System.Globalization;
using System.Net;
using System.Text;
using System.Text.Json;
using XAUPY.Ipc;

namespace XAUPY.Desktop;

public partial class BacktestDashboard
{
    internal static string BuildHtmlReport(BacktestResultSnapshot report,IReadOnlyList<BacktestTradeSnapshot> trades)
    {
        string E(object? value)=>WebUtility.HtmlEncode(Convert.ToString(value,CultureInfo.InvariantCulture) ?? "—");
        var html=new StringBuilder("<!doctype html><html lang=vi><meta charset=utf-8><title>XAUPY • Báo cáo Backtest</title><style>body{font:15px system-ui;max-width:1440px;margin:32px auto;padding:0 20px;color:#18324c}table{border-collapse:collapse;width:100%;margin:20px 0}th,td{padding:9px;border:1px solid #bed1df;text-align:left;overflow-wrap:anywhere}th{background:#e4f1fb}p{line-height:1.6}h1{color:#1264a3}@media print{body{font-size:10px}tr{break-inside:avoid}}</style><h1>XAUPY • Báo cáo Backtest</h1>");
        html.Append($"<p>{E(report.Symbol)} · {E(report.FromDate)} – {E(report.ToDate)}<br>Model: {E(report.Model)}<br>Dataset: {E(report.DatasetFileName)}<br>SHA dữ liệu: {E(report.DatasetFingerprint)}<br>SHA profile: {E(report.ProfileHash)}<br>SHA kết quả: {E(report.ResultHash)}<br>Run: {E(report.RunId)}</p>");
        html.Append($"<p>Vốn đầu: {E(report.InitialBalance)} · Spread giả định OHLC (points): {E(report.SpreadPips)} · Phí khứ hồi / lot: {E(report.CommissionPerLot)}. Replay tick dùng Bid/Ask đã quan sát. Kết quả mô hình không xác nhận khả năng khớp tại broker; chưa bao gồm swap, thanh khoản và độ trễ thực tế.</p><h2>Chỉ tiêu</h2><table><tr><th>Chỉ tiêu</th><th>Giá trị</th></tr>");
        foreach(var p in typeof(BacktestMetrics).GetProperties())html.Append($"<tr><td>{E(p.Name)}</td><td>{E(p.GetValue(report.Metrics))}</td></tr>");
        html.Append("</table><h2>Toàn bộ giao dịch</h2><table><tr><th>#</th><th>Chiều</th><th>Vào (epoch)</th><th>Ra (epoch)</th><th>Giá vào</th><th>Giá ra</th><th>Lot</th><th>Phí</th><th>Lãi ròng</th><th>Lý do</th></tr>");
        foreach(var t in trades)html.Append($"<tr><td>{t.TradeId}</td><td>{E(t.Side)}</td><td>{t.EntryTime}</td><td>{t.ExitTime}</td><td>{E(t.EntryPrice)}</td><td>{E(t.ExitPrice)}</td><td>{E(t.Volume)}</td><td>{E(t.Commission)}</td><td>{E(t.NetPl)}</td><td>{E(t.ExitReason)}</td></tr>");
        html.Append("</table><h2>Cấu hình và giả định của lần chạy</h2><p>Epoch giữ nguyên từ dữ liệu nguồn; giờ trên bảng/biểu đồ dùng offset của dataset, không dùng múi giờ máy tính.</p>");
        if (report.RawResult.ValueKind == JsonValueKind.Object)
            foreach (var name in new[] { "profile", "dataset_metadata", "execution_revision", "execution_assumptions", "tick_evidence", "tick_count", "discontinuous_ticks", "spread_model", "fill_model", "swap_model", "skipped_signals" })
                if (report.RawResult.TryGetProperty(name, out var evidence))
                    html.Append($"<h3>{E(name)}</h3><pre style='white-space:pre-wrap;overflow-wrap:anywhere'>{E(JsonSerializer.Serialize(evidence, new JsonSerializerOptions { WriteIndented=true }))}</pre>");
        return html.Append("</html>").ToString();
    }
}
