using System.Text.Json;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Media;
using Avalonia.Platform.Storage;

namespace XAUPY.Desktop;

public partial class OrdersPositionsDashboard
{
    private object BuildOrdersReport() => new {
        exported_utc = DateTimeOffset.UtcNow,
        snapshot_received_utc = _book.SnapshotReceivedUtc,
        account = _book.AccountLogin,
        account_mode = _book.AccountTradeMode,
        symbol = _book.Symbol ?? _config.Symbol,
        scope = "XAUPY magic only. Snapshot export, not full broker history. Deals: last 50 exits within 7 days. Summary: connected symbol only.",
        all_position_symbols = Check("ShowAllSymbolsCheck").IsChecked == true,
        current_symbol_history = Check("CurrentSymbolHistoryCheck").IsChecked == true,
        positions = _book.Positions.Where(p => Check("ShowAllSymbolsCheck").IsChecked == true || IsCurrentSymbol(p.Symbol)).ToArray(),
        pending_orders = _book.Orders,
        deals = _book.Deals.Where(d => Check("CurrentSymbolHistoryCheck").IsChecked != true || IsCurrentSymbol(d.Symbol)).ToArray(),
        summary = new { _book.OpenPl, _book.RealizedPl, _book.RiskUsd, _book.RiskPct, _book.RiskComplete },
        demo_once = _demoOnceReport,
    };

    private async void ExportOrders_OnClick(object? sender, RoutedEventArgs e)
    {
        try
        {
            if (!_book.Available) throw new InvalidOperationException("Chưa có dữ liệu để xuất.");
            var report = BuildOrdersReport(); // Freeze before opening the picker; ticks continue updating.
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
