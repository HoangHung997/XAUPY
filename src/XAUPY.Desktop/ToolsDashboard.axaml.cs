using System.Globalization;
using System.Text;
using System.Text.Json;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Media;
using Avalonia.Layout;
using Avalonia;
using Avalonia.Input;
using Avalonia.Platform.Storage;
using XAUPY.Ipc;

namespace XAUPY.Desktop;

public partial class ToolsDashboard : UserControl
{
    private EngineProcessSupervisor? _supervisor;
    private string _mode = "editor";
    private bool _loaded;
    private bool _busy;
    private bool _expanded;
    private TextBlock? _lineNumbers;
    private ScrollViewer? _editorScroll;
    private ScrollViewer? _gutterScroll;
    private int _searchNext;
    private readonly List<string> _history = new();
    private static readonly JsonSerializerOptions Pretty = new() { WriteIndented = true };
    private static readonly FilePickerFileType JsonType = new("JSON") { Patterns = new[] { "*.json" } };

    public ToolsDashboard()
    {
        InitializeComponent();
        ToolEditor.TemplateApplied += (_, e) =>
        {
            if (_editorScroll is not null) _editorScroll.ScrollChanged -= EditorScroll_OnChanged;
            _lineNumbers = e.NameScope.Find<TextBlock>("PART_LineNumbers");
            _editorScroll = e.NameScope.Find<ScrollViewer>("PART_ScrollViewer");
            _gutterScroll = e.NameScope.Find<ScrollViewer>("PART_GutterScroll");
            if (_editorScroll is not null) _editorScroll.ScrollChanged += EditorScroll_OnChanged;
            RefreshEditorInfo();
        };
        var icons = new[] { "document", "compare", "bars", "calculator", "globe", "document", "pulse", "link", "user", "transfer" };
        var colors = new[] { "#119DF2", "#04E29C", "#23A1FF", "#FFA744", "#15BDF5", "#B690FB", "#00D9BD", "#6AF1D7", "#BE87ED", "#37ADFF" };
        var index = 0;
        foreach (var button in ToolMenu.Children.OfType<Button>())
        {
            if (button.Content is not StackPanel content) continue;
            var lines = content.Children.OfType<TextBlock>().Select(t => t.Text ?? "").ToArray();
            button.Height = 65;
            button.Padding = new Avalonia.Thickness(7, 5);
            var grid = new Grid { ColumnDefinitions = new ColumnDefinitions("46,*,15"), ColumnSpacing = 10 };
            var icon = new Border { Background = Brush.Parse("#092B49"), CornerRadius = new Avalonia.CornerRadius(6), Child = new ReferenceIcon { Kind = icons[index], Width = 34, Height = 34, Tint = Brush.Parse(colors[index]), HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center } };
            var label = new StackPanel { Spacing = 5, VerticalAlignment = VerticalAlignment.Center };
            label.Children.Add(new TextBlock { Text = lines[0].Length > 4 ? lines[0][4..] : lines[0], FontSize = 15, FontWeight = FontWeight.SemiBold });
            label.Children.Add(new TextBlock { Text = lines.Length > 1 ? lines[1].Trim() : "", FontSize = 13, Foreground = Brush.Parse("#B3D3EF") });
            var arrow = new TextBlock { Text = "›", FontSize = 24, VerticalAlignment = VerticalAlignment.Center };
            Grid.SetColumn(label, 1); Grid.SetColumn(arrow, 2);
            grid.Children.Add(icon); grid.Children.Add(label); grid.Children.Add(arrow);
            button.Content = grid;
            SetMenuAppearance(button, index == 0);
            index++;
        }
    }
    public void AttachSupervisor(EngineProcessSupervisor supervisor) => _supervisor = supervisor;
    public async Task EnsureLoadedAsync(bool force = false)
    {
        if (_busy || (_loaded && !force) || _supervisor?.State != EngineConnectionState.Ready) return;
        await RunAsync(async () =>
        {
            var active = await _supervisor.GetActiveConfigAsync();
            ToolProfileName.Text = active.GetProperty("profile").GetProperty("name").GetString();
            ToolSymbol.Text = active.TryGetProperty("symbol", out var symbol) ? symbol.GetString() : "XAUUSD";
            object display = active;
            if (_mode == "compare")
            {
                var defaults = await _supervisor.GetDefaultConfigAsync();
                var differences = new List<object>();
                Compare("", defaults, active, differences);
                display = new { comparison = "DEFAULT → ACTIVE", differences };
            }
            else if (_mode is "diagnostics" or "bridge" or "indicators" or "symbol" or "export")
            {
                var result = await _supervisor.QueryDiagnosticsAsync();
                EnsureOk(result);
                var diagnostics = result.GetProperty("diagnostics");
                display = _mode switch
                {
                    "bridge" => diagnostics.GetProperty("bridge"),
                    "indicators" => diagnostics.GetProperty("strategy"),
                    "symbol" => new { market = diagnostics.GetProperty("overview"), sessions = active.GetProperty("sessions") },
                    _ => diagnostics
                };
            }
            else if (_mode == "news") display = new { format = "JSON array: timestamp_utc (ISO 8601 + timezone), currency, impact, title", active_filter = active.GetProperty("news"), status = "Mở file lịch tin để kiểm tra; chưa có nguồn lịch tin trực tiếp." };
            else if (_mode == "risk") display = new { status = "Nhập risk budget, khoảng SL, tick size và tick value rồi nhấn Tính lot.", note = "Ví dụ nhập tay; chưa dùng để đặt lệnh. Không bao gồm spread, commission hoặc slippage." };
            ToolEditor.Text = JsonSerializer.Serialize(display, Pretty);
            RefreshEditorInfo();
            _loaded = true;
            Result("Đã tải dữ liệu thực từ Python Engine.", true);
        });
    }

    private async void SelectTool_OnClick(object? sender, RoutedEventArgs e)
    {
        if (sender is not Button button || button.Tag is not string mode) return;
        _mode = mode;
        foreach (var child in ToolMenu.Children.OfType<Button>()) SetMenuAppearance(child, child == button);
        var title = (button.Content as Grid)?.Children.OfType<StackPanel>().FirstOrDefault()?.Children.OfType<TextBlock>().FirstOrDefault()?.Text ?? mode;
        ToolTitle.Text = title;
        SelectedToolName.Text = title;
        var icon = (button.Content as Grid)?.Children.OfType<Border>().FirstOrDefault()?.Child as ReferenceIcon;
        ToolHeaderIcon.Kind = SelectedToolIcon.Kind = icon?.Kind ?? "document";
        ToolEditor.IsReadOnly = mode is not ("editor" or "profile" or "news");
        ApplyToolButton.IsEnabled = mode is "editor" or "profile";
        SaveProfileButton.IsEnabled = DefaultProfileButton.IsEnabled = ApplyToolButton.IsEnabled;
        RiskInputs.IsVisible = mode == "risk";
        HistoryInputs.IsVisible = mode == "export";
        ToolSubtitle.Text = mode is "editor" or "profile" ? "Chỉnh sửa cấu hình chuẩn; kiểm tra cú pháp và áp dụng nhanh." : "Kiểm tra dữ liệu thực, lưu báo cáo và đối chiếu trạng thái hệ thống.";
        await EnsureLoadedAsync(true);
    }

    private async void Reload_OnClick(object? sender, RoutedEventArgs e) => await EnsureLoadedAsync(true);
    private static void SetMenuAppearance(Button button, bool selected)
    {
        button.Background = new LinearGradientBrush
        {
            StartPoint = new RelativePoint(0, 0, RelativeUnit.Relative), EndPoint = new RelativePoint(1, 1, RelativeUnit.Relative),
            GradientStops = new GradientStops { new(selected ? Color.Parse("#073D83") : Color.Parse("#06233D"), 0), new(Color.Parse("#02182E"), 1) }
        };
        button.BorderBrush = Brush.Parse(selected ? "#1287FF" : "#174765");
        if (button.Content is Grid grid && grid.Children.OfType<Border>().FirstOrDefault() is { } tile)
            tile.Background = Brush.Parse(selected ? "#0868F4" : "#082844");
    }
    private void EditorScroll_OnChanged(object? sender, ScrollChangedEventArgs e)
    {
        if (_gutterScroll is not null && _editorScroll is not null) _gutterScroll.Offset = new Vector(0, _editorScroll.Offset.Y);
    }
    private void Editor_OnTextChanged(object? sender, TextChangedEventArgs e)
    {
        if (EditorFileInfo is null) return;
        RefreshEditorInfo();
        EditorValidation.Text = "●  Chưa kiểm tra";
        EditorValidation.Foreground = Brushes.Gold;
        _searchNext = 0;
    }
    private void RefreshEditorInfo()
    {
        var text = ToolEditor.Text ?? "";
        var count = text.Count(c => c == '\n') + 1;
        if (_lineNumbers is not null) _lineNumbers.Text = string.Join('\n', Enumerable.Range(1, count));
        EditorFileInfo.Text = $"Số dòng          {count:N0}\nKích thước       {Encoding.UTF8.GetByteCount(text) / 1024.0:0.00} KB\nCập nhật          {DateTime.Now:HH:mm:ss}";
    }
    private void Find_OnClick(object? sender, RoutedEventArgs e)
    {
        EditorSearchBar.IsVisible = true;
        EditorSearchText.Focus();
        EditorSearchText.SelectAll();
    }
    private void CloseSearch_OnClick(object? sender, RoutedEventArgs e) { EditorSearchBar.IsVisible = false; ToolEditor.Focus(); }
    private void FindNext_OnClick(object? sender, RoutedEventArgs e)
    {
        var query = EditorSearchText.Text ?? "";
        var text = ToolEditor.Text ?? "";
        if (query.Length == 0) { EditorSearchStatus.Text = "Nhập từ cần tìm"; return; }
        var index = text.IndexOf(query, Math.Min(_searchNext, text.Length), StringComparison.OrdinalIgnoreCase);
        if (index < 0) index = text.IndexOf(query, StringComparison.OrdinalIgnoreCase);
        if (index < 0) { EditorSearchStatus.Text = "Không tìm thấy"; return; }
        ToolEditor.CaretIndex = index + query.Length;
        ToolEditor.SelectionStart = index;
        ToolEditor.SelectionEnd = index + query.Length;
        _searchNext = index + query.Length;
        EditorSearchStatus.Text = $"Dòng {text[..index].Count(c => c == '\n') + 1}";
        ToolEditor.Focus();
    }
    private void Search_OnKeyDown(object? sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter) { FindNext_OnClick(sender, new RoutedEventArgs()); e.Handled = true; }
        else if (e.Key == Key.Escape) { CloseSearch_OnClick(sender, new RoutedEventArgs()); e.Handled = true; }
    }
    private void Expand_OnClick(object? sender, RoutedEventArgs e)
    {
        _expanded = !_expanded;
        ToolNavigation.IsVisible = ToolHelpColumn.IsVisible = !_expanded;
        ToolsLayout.ColumnDefinitions = new ColumnDefinitions(_expanded ? "0,*,0" : "330,*,320");
        ExpandEditorButton.Content = _expanded ? "⛶  Thu gọn" : "⛶  Toàn màn hình";
    }
    private void Tools_OnKeyDown(object? sender, KeyEventArgs e)
    {
        if (e.KeyModifiers == (KeyModifiers.Control | KeyModifiers.Shift) && e.Key == Key.F) Format_OnClick(sender, new RoutedEventArgs());
        else if (e.KeyModifiers == KeyModifiers.Control && e.Key == Key.F) Find_OnClick(sender, new RoutedEventArgs());
        else if (e.KeyModifiers == KeyModifiers.Control && e.Key == Key.S) Apply_OnClick(sender, new RoutedEventArgs());
        else if (e.Key == Key.F11) Expand_OnClick(sender, new RoutedEventArgs());
        else return;
        e.Handled = true;
    }
    private async void Defaults_OnClick(object? sender, RoutedEventArgs e) => await RunAsync(async () =>
    {
        if (_supervisor is null || _mode is not ("editor" or "profile")) return;
        ToolEditor.Text = JsonSerializer.Serialize(await _supervisor.GetDefaultConfigAsync(), Pretty);
        Result("Đã nạp mặc định vào bản nháp.", true);
        ToolResultDetail.Text = "Kiểm tra và nhấn Áp dụng nếu muốn thay cấu hình đang chạy.";
    });
    private void Help_OnClick(object? sender, RoutedEventArgs e)
    {
        Result("Mở hoặc chỉnh sửa JSON → kiểm tra cú pháp → áp dụng.", true);
        ToolResultDetail.Text = "Ctrl+F tìm kiếm • Ctrl+Shift+F định dạng • Ctrl+S lưu profile • F11 mở rộng. Sao lưu/khôi phục tại Cài đặt.";
    }
    private async void HistoryStart_OnClick(object? sender, RoutedEventArgs e) => await RunAsync(async () =>
    {
        if (_supervisor is null) return;
        var response = await _supervisor.StartHistoryDownloadAsync(HistoryTerminal.Text ?? "", HistorySymbol.Text ?? "");
        EnsureOk(response);
        ToolEditor.Text = JsonSerializer.Serialize(response.GetProperty("history_download"), Pretty);
        Result("Đang tải lịch sử trên tiến trình riêng. Nhấn Tiến độ để xem số nến và thư mục CSV.", true);
    });
    private async void HistoryStatus_OnClick(object? sender, RoutedEventArgs e) => await RunAsync(async () =>
    {
        if (_supervisor is null) return;
        var response = await _supervisor.GetHistoryDownloadAsync();
        EnsureOk(response);
        ToolEditor.Text = JsonSerializer.Serialize(response.GetProperty("history_download"), Pretty);
        Result("Đã cập nhật số nến, độ phủ và giới hạn dữ liệu từ MT5.", true);
    });
    private void Format_OnClick(object? sender, RoutedEventArgs e)
    {
        try { using var json = JsonDocument.Parse(ToolEditor.Text ?? ""); ToolEditor.Text = JsonSerializer.Serialize(json.RootElement, Pretty); Result("Đã định dạng JSON.", true); }
        catch (JsonException ex) { Result(ex.Message, false); }
    }
    private async void Validate_OnClick(object? sender, RoutedEventArgs e) => await RunAsync(async () =>
    {
        using var json = JsonDocument.Parse(ToolEditor.Text ?? "");
        if (_mode == "news")
        {
            if (json.RootElement.ValueKind != JsonValueKind.Array) throw new InvalidDataException("Lịch tin phải là mảng JSON.");
            var count = 0;
            foreach (var item in json.RootElement.EnumerateArray())
            {
                if (!item.TryGetProperty("timestamp_utc", out var time) || !DateTimeOffset.TryParse(time.GetString(), CultureInfo.InvariantCulture, DateTimeStyles.None, out _) ||
                    !item.TryGetProperty("currency", out var currency) || currency.GetString()?.Length != 3 ||
                    !item.TryGetProperty("impact", out var impact) || impact.GetString() is not ("HIGH" or "MEDIUM" or "LOW") ||
                    !item.TryGetProperty("title", out var title) || string.IsNullOrWhiteSpace(title.GetString()))
                    throw new InvalidDataException($"Tin số {count + 1}: cần timestamp_utc, currency (3 ký tự), impact HIGH/MEDIUM/LOW và title.");
                count++;
            }
            Result($"Lịch tin JSON hợp lệ: {count} sự kiện. Chỉ kiểm tra file, chưa kích hoạt news feed.", true);
        }
        else if (_mode is "editor" or "profile")
        {
            if (_supervisor is null) return;
            var result = await _supervisor.ValidateConfigAsync(json.RootElement);
            Result(result.Valid ? "Cú pháp JSON và schema cấu hình hợp lệ." : string.Join(" • ", result.Errors), result.Valid);
            EditorValidation.Text = result.Valid ? "●  Hợp lệ (Valid)" : "●  Cấu hình không hợp lệ";
            EditorValidation.Foreground = result.Valid ? Brushes.SpringGreen : Brushes.OrangeRed;
        }
        else Result("Cú pháp JSON hợp lệ.", true);
    });
    private async void Apply_OnClick(object? sender, RoutedEventArgs e) => await RunAsync(async () =>
    {
        if (_supervisor is null || _mode is not ("editor" or "profile")) return;
        using var json = JsonDocument.Parse(ToolEditor.Text ?? "");
        var result = await _supervisor.ApplyActiveConfigAsync(json.RootElement);
        Result(result.Applied ? "Đã áp dụng và lưu profile. Guardian tiếp tục khóa execution." : string.Join(" • ", result.Errors), result.Applied);
    });
    private async void Open_OnClick(object? sender, RoutedEventArgs e) => await RunAsync(async () =>
    {
        var top = TopLevel.GetTopLevel(this);
        if (top is null) return;
        var paths = await top.StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions { Title = "Mở JSON", AllowMultiple = false, FileTypeFilter = new[] { JsonType } });
        if (paths.Count == 0) return;
        await using var stream = await paths[0].OpenReadAsync();
        if (stream.CanSeek && stream.Length > 2 * 1024 * 1024) throw new InvalidDataException("File vượt quá 2 MiB.");
        using var reader = new StreamReader(stream, Encoding.UTF8);
        var text = await reader.ReadToEndAsync();
        using var json = JsonDocument.Parse(text);
        ToolEditor.Text = JsonSerializer.Serialize(json.RootElement, Pretty);
        ToolFileName.Text = paths[0].Name;
        if (_mode != "news") { _mode = "profile"; ToolEditor.IsReadOnly = false; ApplyToolButton.IsEnabled = SaveProfileButton.IsEnabled = DefaultProfileButton.IsEnabled = true; }
        Result("Đã mở file. Nhấn Kiểm tra cú pháp trước khi áp dụng.", true);
    });
    private async void Save_OnClick(object? sender, RoutedEventArgs e) => await RunAsync(async () =>
    {
        var top = TopLevel.GetTopLevel(this);
        if (top is null) return;
        var target = await top.StorageProvider.SaveFilePickerAsync(new FilePickerSaveOptions { Title = "Lưu JSON", SuggestedFileName = $"xaupy-{_mode}.json", DefaultExtension = "json", FileTypeChoices = new[] { JsonType } });
        if (target is null) return;
        using var json = JsonDocument.Parse(ToolEditor.Text ?? "");
        await using var stream = await target.OpenWriteAsync();
        stream.SetLength(0);
        await JsonSerializer.SerializeAsync(stream, json.RootElement, Pretty);
        Result($"Đã lưu {target.Name}.", true);
    });
    private void CalculateRisk_OnClick(object? sender, RoutedEventArgs e)
    {
        try
        {
            double Number(TextBox box) => double.TryParse(box.Text, NumberStyles.Float, CultureInfo.InvariantCulture, out var n) && double.IsFinite(n) && n > 0 ? n : throw new InvalidDataException("Các giá trị phải là số dương.");
            var budget = Number(RiskBudget); var distance = Number(RiskDistance); var size = Number(RiskTickSize); var value = Number(RiskTickValue);
            var lossPerLot = distance / size * value;
            ToolEditor.Text = JsonSerializer.Serialize(new { budget_usd = budget, sl_distance = distance, tick_size = size, tick_value_per_lot = value, risk_per_lot = lossPerLot, theoretical_lots = budget / lossPerLot, warning = "Làm tròn xuống theo volume_step của broker. Chưa bao gồm phí và slippage; đây là tính toán tham khảo." }, Pretty);
            Result("Đã tính lot lý thuyết; kiểm tra thông số hợp đồng trước khi sử dụng.", true);
        }
        catch (Exception ex) { Result(ex.Message, false); }
    }
    private async Task RunAsync(Func<Task> action)
    {
        if (_busy) return; _busy = true;
        try { await action(); } catch (Exception ex) { Result(ex.Message, false); } finally { _busy = false; }
    }
    private void Result(string message, bool ok)
    {
        ToolResult.Text = message; ToolResult.Foreground = ok ? Brushes.SpringGreen : Brushes.OrangeRed;
        ToolResultBadge.Background = ok ? Brush.Parse("#08D690") : Brushes.OrangeRed;
        ToolResultIcon.Text = ok ? "✓" : "!";
        ToolResultDetail.Text = ok ? "Thao tác hoàn tất. Cấu hình chỉ thay đổi khi áp dụng." : "Kiểm tra thông tin và thử lại.";
        ToolResultMeta.Text = $"Thời gian: {DateTime.Now:HH:mm:ss}\nSố dòng: {(ToolEditor.Text ?? "").Count(c => c == '\n') + 1}";
        _history.Insert(0, $"{DateTime.Now:HH:mm:ss}  {message}");
        ToolHistory.Text = string.Join("\n", _history.Take(15));
    }
    private static void EnsureOk(JsonElement value) { if (!value.GetProperty("ok").GetBoolean()) throw new InvalidDataException(value.GetProperty("errors").ToString()); }
    private static void Compare(string path, JsonElement baseline, JsonElement active, List<object> output)
    {
        if (baseline.ValueKind == JsonValueKind.Object && active.ValueKind == JsonValueKind.Object)
        {
            foreach (var field in baseline.EnumerateObject()) if (active.TryGetProperty(field.Name, out var other)) Compare(path.Length == 0 ? field.Name : path + "." + field.Name, field.Value, other, output);
        }
        else if (baseline.ToString() != active.ToString()) output.Add(new { path, baseline = baseline.Clone(), active = active.Clone() });
    }
}
