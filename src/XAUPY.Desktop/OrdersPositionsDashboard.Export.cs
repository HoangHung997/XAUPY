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

    private async void ExportOrders_OnClick(object? sender, RoutedEventArgs e)
    {
        try
        {
            if (!_book.Available) throw new InvalidOperationException("Chưa có dữ liệu để xuất.");
            var report = BuildOrdersReport(await AllBrokerHistoryAsync());
            var storage = TopLevel.GetTopLevel(this)?.StorageProvider;
            if (storage is null) return;
            var file = await storage.SaveFilePickerAsync(new FilePickerSaveOptions {
                Title = "Xuất báo cáo Lệnh & Vị thế", SuggestedFileName = $"XAUPY-orders-{DateTime.Now:yyyyMMdd-HHmmss}.json",
                DefaultExtension = "json", FileTypeChoices = new[] { new FilePickerFileType("Báo cáo JSON") { Patterns = new[] { "*.json" } } }
            });
            if (file is null) return;
            await using var stream = await file.OpenWriteAsync(); stream.SetLength(0);
            await JsonSerializer.SerializeAsync(stream, report, new JsonSerializerOptions { WriteIndented = true });
            SetActionStatus($"Đã xuất {file.Name} • dữ liệu tại thời điểm mở hộp lưu.", Brushes.LightGreen);
        }
        catch (Exception error) { SetActionStatus(error.Message, Brushes.IndianRed); }
    }
}
