using Avalonia.Controls;
using Avalonia.Interactivity;

namespace XAUPY.Desktop;

public partial class MainWindow : Window
{
    private static readonly IReadOnlyDictionary<string, (string Title, string Subtitle)> Pages =
        new Dictionary<string, (string, string)>
        {
            ["overview"] = ("Tổng quan", "Foundation shell: xác nhận stack Avalonia/.NET có thể build và phát hành qua GitHub CI."),
            ["configuration"] = ("Cấu hình", "Placeholder Task 001. Full profile/config editor sẽ được triển khai ở task chuyên biệt."),
            ["strategy"] = ("Chiến lược", "Placeholder Task 001. Direction → Pullback → Trigger thuộc strategy task, chưa chạy giao dịch."),
            ["monitoring"] = ("Giám sát", "Placeholder Task 001. Realtime MT5/Python/Bridge monitoring chưa được kết nối."),
            ["orders"] = ("Lệnh & Vị thế", "Placeholder Task 001. Không có execution code hoặc broker commands."),
            ["backtest"] = ("Backtest", "Placeholder Task 001. Backtest parity engine sẽ được triển khai sau strategy engine."),
            ["optimization"] = ("Tối ưu", "Placeholder Task 001. Parameter sweep/walk-forward chưa được triển khai."),
            ["logs"] = ("Nhật ký", "Placeholder Task 001. Structured logging schema sẽ được triển khai cùng IPC/Bridge."),
            ["tools"] = ("Công cụ", "Placeholder Task 001. Diagnostics và config utilities thuộc task sau."),
            ["settings"] = ("Cài đặt", "Placeholder Task 001. Connection, backup và startup settings chưa có hiệu lực.")
        };

    public MainWindow()
    {
        InitializeComponent();
    }

    private void NavButton_OnClick(object? sender, RoutedEventArgs e)
    {
        if (sender is not Button { Tag: string key } || !Pages.TryGetValue(key, out var page))
            return;

        this.FindControl<TextBlock>("PageTitle")!.Text = page.Title;
        this.FindControl<TextBlock>("PageSubtitle")!.Text = page.Subtitle;
    }
}
