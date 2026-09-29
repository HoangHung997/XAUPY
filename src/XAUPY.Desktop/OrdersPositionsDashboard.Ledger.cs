using System.Text.Json;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Platform.Storage;
using XAUPY.Ipc;

namespace XAUPY.Desktop;

public partial class OrdersPositionsDashboard
{
    private async void ExecutionHistory_OnClick(object? sender, RoutedEventArgs e)
    {
        if (_supervisor is null || TopLevel.GetTopLevel(this) is not Window owner) return;
        using var lifetime = new CancellationTokenSource();
        var status = new TextBlock { TextWrapping = TextWrapping.Wrap, Foreground = Brushes.Gold };
        var list = new ListBox { MinHeight = 160 };
        var detail = new TextBox { IsReadOnly = true, AcceptsReturn = true, TextWrapping = TextWrapping.NoWrap,
            FontFamily = new FontFamily("Consolas"), FontSize = 12 };
        var refresh = new Button { [LocalizationService.TextProperty] = "Làm mới", Classes = { "secondary" } };
        var previous = new Button { Content = "‹", Classes = { "secondary" } };
        var next = new Button { Content = "›", Classes = { "secondary" } };
        var export = new Button { [LocalizationService.TextProperty] = "Xuất trang JSON", Classes = { "secondary" } };
        var close = new Button { [LocalizationService.TextProperty] = "Đóng", Classes = { "secondary" } };
        var buttons = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8,
            Children = { refresh, previous, next, export, close } };
        var grid = new Grid { Margin = new Thickness(16), RowDefinitions = new RowDefinitions("Auto,Auto,2*,3*,Auto"), RowSpacing = 10 };
        grid.Children.Add(new TextBlock { Text = "Sổ thực thi của app • gồm các tài khoản đã dùng. Chọn dòng để xem yêu cầu và bằng chứng broker.", TextWrapping = TextWrapping.Wrap });
        Grid.SetRow(status, 1); grid.Children.Add(status);
        Grid.SetRow(list, 2); grid.Children.Add(list);
        Grid.SetRow(detail, 3); grid.Children.Add(detail);
        Grid.SetRow(buttons, 4); grid.Children.Add(buttons);
        var window = new Window { [LocalizationService.TitleProperty] = "Tiến trình lệnh — chỉ đọc, không gửi lại", Width = 950, Height = 700,
            MinWidth = 600, MinHeight = 420, WindowStartupLocation = WindowStartupLocation.CenterOwner,
            Content = grid, Background = new SolidColorBrush(Color.Parse("#031426")) };
        JsonElement[] rows = Array.Empty<JsonElement>();
        JsonElement? pageData = null;
        int page = 0;
        double? cutoff = null;
        bool busy = false;
        async Task Load(int requestedPage, bool reset)
        {
            if (busy || lifetime.IsCancellationRequested) return;
            busy = true;
            try
            {
                var response = await _supervisor.ExecutionRequestAsync("execution_history", new {
                    limit = 50, offset = requestedPage*50, snapshot_time = reset ? null : cutoff
                }, lifetime.Token);
                if (!response.TryGetProperty("accepted", out var accepted) || accepted.ValueKind != JsonValueKind.True)
                    throw new InvalidDataException(response.TryGetProperty("code", out var code) ? ExecutionPresentation.Reason(code.ToString()) : "Không đọc được sổ thực thi.");
                pageData = response.Clone();
                rows = response.GetProperty("items").EnumerateArray().Select(v => v.Clone()).ToArray();
                page = requestedPage;
                cutoff = response.GetProperty("snapshot_time").GetDouble();
                list.ItemsSource = rows.Select(LedgerCaption).ToArray();
                if (rows.Length > 0) list.SelectedIndex = 0; else detail.Text = "Chưa có yêu cầu thực thi được xếp hàng. Lỗi kiểm tra trước gửi xem ở Nhật ký → Orders.";
                int total = response.GetProperty("total").GetInt32();
                status.Text = $"Trang {page+1} • {total} yêu cầu • tập ID cố định tại {DateTimeOffset.FromUnixTimeMilliseconds((long)(cutoff*1000)).ToLocalTime():yyyy-MM-dd HH:mm:ss}. Trạng thái từng ID được đọc mới; KHÔNG tự gửi lại.";
                previous.IsEnabled = page > 0;
                next.IsEnabled = response.GetProperty("has_more").GetBoolean();
            }
            catch (OperationCanceledException) when (lifetime.IsCancellationRequested) { }
            catch (Exception ex) { status.Text = ex.Message; }
            finally { busy = false; }
        }
        list.SelectionChanged += (_, _) =>
        {
            if (list.SelectedIndex >= 0 && list.SelectedIndex < rows.Length)
                detail.Text = JsonSerializer.Serialize(rows[list.SelectedIndex], new JsonSerializerOptions { WriteIndented = true });
        };
        refresh.Click += async (_, _) => await Load(0, true);
        previous.Click += async (_, _) => { if (page > 0) await Load(page-1, false); };
        next.Click += async (_, _) => await Load(page+1, false);
        export.Click += async (_, _) =>
        {
            if (pageData is not { } frozen) return;
            try
            {
                var file = await window.StorageProvider.SaveFilePickerAsync(new FilePickerSaveOptions {
                    Title = LocalizationService.T("Xuất bằng chứng thực thi"), SuggestedFileName = $"XAUPY-execution-page-{page+1}.json", DefaultExtension = "json",
                    FileTypeChoices = new[] { new FilePickerFileType("JSON") { Patterns = new[] { "*.json" } } }
                });
                if (file is not null)
                {
                    await FileOutput.WriteTextAsync(file, JsonSerializer.Serialize(frozen, new JsonSerializerOptions { WriteIndented = true }), lifetime.Token);
                    status.Text = $"Đã xuất {file.Name}. Bằng chứng chỉ đọc; không thay đổi quyền hoặc lệnh.";
                }
            }
            catch (Exception ex) { status.Text = ex.Message; }
        };
        close.Click += (_, _) => window.Close();
        window.Closed += (_, _) => lifetime.Cancel();
        window.Opened += async (_, _) => await Load(0, true);
        await window.ShowDialog(owner);
    }

    internal static string LedgerCaption(JsonElement item)
    {
        string id = item.GetProperty("id").GetString() ?? "";
        string state = item.GetProperty("state").GetString() ?? "UNKNOWN";
        var command = item.GetProperty("command");
        string Read(string key) => command.TryGetProperty(key, out var value) ? value.ToString() : "—";
        string when = item.TryGetProperty("created", out var date) && date.TryGetDouble(out double stamp) && double.IsFinite(stamp)
            ? DateTimeOffset.FromUnixTimeMilliseconds((long)(stamp*1000)).ToLocalTime().ToString("MM-dd HH:mm:ss") : "—";
        return $"{when} · {Read("account_login")} / {Read("symbol")} · {Read("action")} · {state} · {id[..Math.Min(id.Length,12)]}";
    }
}
