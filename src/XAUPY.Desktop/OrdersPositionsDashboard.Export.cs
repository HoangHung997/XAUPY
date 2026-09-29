using System.Text.Json;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Media;
using Avalonia.Platform.Storage;

namespace XAUPY.Desktop;

public partial class OrdersPositionsDashboard
{
    private object BuildOrdersReport(JsonElement[] history) => new {
        exported_utc = DateTimeOffset.UtcNow,
        snapshot_received_utc = _book.SnapshotReceivedUtc,
        trade_time_basis = "MT5 server wall clock; preserved epoch fields, no machine timezone conversion",
        account = _book.AccountLogin,
        account_mode = _book.AccountTradeMode,
        symbol = _book.Symbol ?? _config.Symbol,
        scope = "XAUPY magic only. All imported broker exit deals matching selected symbol filter. Entry/exit fees allocated by closed volume. Summary: connected symbol only.",
        broker_history_report = _brokerHistoryReportId,
        all_position_symbols = Check("ShowAllSymbolsCheck").IsChecked == true,
        current_symbol_history = Check("CurrentSymbolHistoryCheck").IsChecked == true,
        positions = _book.Positions.Where(p => Check("ShowAllSymbolsCheck").IsChecked == true || IsCurrentSymbol(p.Symbol)).ToArray(),
        pending_orders = _book.Orders,
        deals = history,
        summary = new { _book.OpenPl, _book.RealizedPl, _book.RiskUsd, _book.RiskPct, _book.RiskComplete },
        demo_once = _demoOnceReport,
    };

    internal static string BrokerHistoryCsv(IEnumerable<JsonElement> history)
    {
        string[] fields = ["ticket","order_ticket","position_id","magic","symbol","side","entry","volume",
            "time","price_in","price_out","sl","tp","profit","entry_costs","exit_costs","commission","swap",
            "realized_total","entry_complete","reason","comment"];
        var text = new System.Text.StringBuilder();
        text.AppendLine(string.Join(",",fields));
        foreach (var row in history)
            text.AppendLine(string.Join(",",fields.Select(field => row.TryGetProperty(field,out var value) ? Cell(value) : "")));
        return text.ToString();
        static string Cell(JsonElement value)
        {
            if (value.ValueKind is JsonValueKind.Null or JsonValueKind.Undefined) return "";
            if (value.ValueKind != JsonValueKind.String) return value.GetRawText();
            string text = value.GetString() ?? "";
            // Spreadsheet tools must treat broker/user comments as data, not formulas.
            if (text.Length > 0 && ("=+-@\t\r\n".Contains(text[0]) || text.TrimStart().StartsWith('='))) text = "'" + text;
            return "\"" + text.Replace("\"","\"\"") + "\"";
        }
    }

    private async void ExportOrders_OnClick(object? sender, RoutedEventArgs e)
    {
        try
        {
            if (!_book.Available) throw new InvalidOperationException("Chưa có dữ liệu để xuất.");
            var history = await AllBrokerHistoryAsync();
            var report = BuildOrdersReport(history);
            var storage = TopLevel.GetTopLevel(this)?.StorageProvider;
            if (storage is null) return;
            var file = await storage.SaveFilePickerAsync(new FilePickerSaveOptions {
                Title = LocalizationService.T("Xuất báo cáo Lệnh & Vị thế"), SuggestedFileName = $"XAUPY-orders-{DateTime.Now:yyyyMMdd-HHmmss}.json",
                DefaultExtension = "json", FileTypeChoices = new[] {
                    new FilePickerFileType("Báo cáo đầy đủ JSON") { Patterns = new[] { "*.json" } },
                    new FilePickerFileType("Lịch sử broker CSV (UTF-8)") { Patterns = new[] { "*.csv" } } }
            });
            if (file is null) return;
            string content = file.Name.EndsWith(".csv", StringComparison.OrdinalIgnoreCase)
                ? BrokerHistoryCsv(history) : JsonSerializer.Serialize(report,new JsonSerializerOptions { WriteIndented = true });
            await FileOutput.WriteTextAsync(file,content);
            SetActionStatus($"Đã xuất {file.Name} • dữ liệu tại thời điểm mở hộp lưu.", Brushes.LightGreen);
        }
        catch (Exception error) { SetActionStatus(error.Message, Brushes.IndianRed); }
    }
}
