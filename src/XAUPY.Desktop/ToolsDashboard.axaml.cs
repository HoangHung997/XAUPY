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
    private string _loadedText = "";
    private JsonElement? _baselineProfile;
    private WindowState _previousWindowState;
    private IStorageFile? _currentFile;
    public bool HasUnsavedChanges => _loaded && !ToolEditor.IsReadOnly && (ToolEditor.Text ?? "") != _loadedText;
    public Func<bool>? HasConflictingDraft { get; set; }
    private readonly List<string> _history = new();
    private static readonly JsonSerializerOptions Pretty = new() { WriteIndented = true,
        Encoder = System.Text.Encodings.Web.JavaScriptEncoder.Create(System.Text.Unicode.UnicodeRanges.All) };
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
            var lines = content.Children.OfType<TextBlock>().ToArray();
            content.Children.Clear();
            button.Height = 65;
            button.Padding = new Avalonia.Thickness(7, 5);
            var grid = new Grid { ColumnDefinitions = new ColumnDefinitions("46,*,15"), ColumnSpacing = 10 };
            var icon = new Border { Background = Brush.Parse("#092B49"), CornerRadius = new Avalonia.CornerRadius(6), Child = new ReferenceIcon { Kind = icons[index], Width = 34, Height = 34, Tint = Brush.Parse(colors[index]), HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center } };
            var label = new StackPanel { Spacing = 5, VerticalAlignment = VerticalAlignment.Center };
            lines[0].SetValue(AppearanceService.BaseFontSizeProperty, 15d);
            lines[0].FontWeight = FontWeight.SemiBold;
            lines[1].SetValue(AppearanceService.BaseFontSizeProperty, 13d);
            lines[1].Foreground = Brush.Parse("#B3D3EF");
            label.Children.Add(lines[0]); label.Children.Add(lines[1]);
            var arrow = new TextBlock { Text = "›", [AppearanceService.BaseFontSizeProperty] = 24d, VerticalAlignment = VerticalAlignment.Center };
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
        if (_busy || HasUnsavedChanges || (_loaded && !force) || _supervisor?.State != EngineConnectionState.Ready) return;
        await RunAsync(async () =>
        {
            var active = await _supervisor.GetActiveConfigAsync();
            ToolProfileName.Text = active.GetProperty("profile").GetProperty("name").GetString();
            ToolSymbol.Text = active.GetProperty("strategy").GetProperty("symbol").GetString();
            _baselineProfile = active.Clone();
            object display = active;
            string message = "Đã tải dữ liệu thực từ Python Engine.";
            bool checksPassed = true;
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
                    "indicators" => diagnostics.GetProperty("indicator_comparison"),
                    "symbol" => new { broker = diagnostics.GetProperty("broker_metadata"), configured_sessions = active.GetProperty("sessions") },
                    _ => diagnostics
                };
                if (_mode == "indicators")
                {
                    var comparison = diagnostics.GetProperty("indicator_comparison");
                    var rows = comparison.GetProperty("rows").EnumerateArray().ToArray();
                    int passed = rows.Count(row => row.GetProperty("status").GetString() == "PASS");
                    checksPassed = rows.Length > 0 && passed == rows.Length;
                    message = $"Đối chiếu MT5 / Python: {passed}/{rows.Length} đạt sai số cho phép. Chi tiết từng khung ở bảng dữ liệu.";
                }
            }
            else if (_mode == "news")
            {
                var calendar=await _supervisor.GetCalendarAsync(); EnsureOk(calendar);
                display=calendar.GetProperty("calendar").ValueKind==JsonValueKind.Object ? calendar.GetProperty("calendar") : new {
                    coverage_start_utc=DateTimeOffset.UtcNow.ToString("O"),coverage_end_utc=DateTimeOffset.UtcNow.AddDays(7).ToString("O"),
                    events=Array.Empty<object>() };
            }
            else if (_mode == "risk") display = new { status = "Nhập ngân sách rủi ro, khoảng SL và đặc tả hợp đồng rồi nhấn Tính lot.", note = "Kết quả gồm spread hiện tại, phí và trượt giá đã cấu hình; dùng để tính tham khảo. Khối lượng khi đặt lệnh được kiểm lại theo dữ liệu broker mới nhất." };
            ToolEditor.Text = JsonSerializer.Serialize(display, Pretty);
            ToolFileName.Text = _mode is "editor" or "profile" ? "active-profile.json" : $"{_mode}-report.json";
            _loadedText = ToolEditor.Text;
            RefreshEditorInfo();
            _loaded = true;
            Result(message, checksPassed);
        });
    }

    private async void SelectTool_OnClick(object? sender, RoutedEventArgs e)
    {
        if (sender is not Button button || button.Tag is not string mode) return;
        if (_busy || !await ConfirmDiscardDraftAsync()) return;
        _loaded = false;
        _mode = mode;
        _currentFile = null;
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
        LibraryInputs.IsVisible = mode == "profile";
        CompareInputs.IsVisible = mode == "compare";
        ApplyToolButton.IsEnabled = mode is "editor" or "profile" or "news";
        SelectedToolDescription.Text = mode switch
        {
            "compare" => "Đối chiếu cấu hình đang dùng với mặc định hoặc hai file đã chọn.",
            "indicators" => "Đối chiếu RSI, EMA và Z-score giữa MT5 và Python trên cùng nến đóng.",
            "risk" => "Tính lot từ ngân sách, khoảng SL, phí và đặc tả hợp đồng.",
            "symbol" => "Xem đặc tả hợp đồng và lịch phiên broker đang trả về.",
            "news" => "Kiểm tra và nhập lịch tin có thời gian, tiền tệ và mức ảnh hưởng.",
            "diagnostics" => "Kiểm tra dữ liệu, kết nối và thư mục vận hành.",
            "bridge" => "Đọc trạng thái EA Bridge và tuổi dữ liệu gần nhất.",
            "profile" => "Lưu các phiên bản cấu hình, mở lại vào bản nháp và quản lý hồ sơ khởi động.",
            "export" => "Chuyển dữ liệu phân tích bằng ZIP và tải lịch sử nến, tick từ MT5.",
            _ => "Chỉnh sửa và kiểm tra cấu hình trước khi áp dụng."
        };
        ToolSubtitle.Text = SelectedToolDescription.Text;
        SelectedToolCapabilities.Text = mode switch
        {
            "export" => "✓ Xuất / nhập ZIP có kiểm tra toàn vẹn\n✓ Tải nến của 9 khung\n✓ Tải tick Bid/Ask theo ngày\n✓ Xem tiến độ và hủy tác vụ\n✓ Giữ cấu hình hiện tại khi nhập",
            "indicators" => "✓ RSI 7 / 14 / 20, EMA 20, Z 20\n✓ Đối chiếu 9 khung thời gian\n✓ Sai số và dữ liệu khởi tạo\n✓ Tải lại số đo mới\n✓ Lưu báo cáo JSON",
            "profile" => "✓ Lưu từng phiên bản\n✓ Mở lại vào bản nháp\n✓ Kiểm tra cấu hình\n✓ Áp dụng khi người dùng chọn\n✓ Bỏ hồ sơ khởi động riêng",
            "news" => "✓ Kiểm cú pháp và thời gian\n✓ Xác định phạm vi bao phủ\n✓ Kiểm tiền tệ và mức ảnh hưởng\n✓ Áp dụng vào bộ lọc tin\n✓ Lưu thành file JSON",
            "editor" => "✓ Chỉnh sửa cấu hình\n✓ Kiểm JSON và schema\n✓ Lưu bản nháp ra file\n✓ Áp dụng vào hệ thống\n✓ Giữ bản nháp khi có xung đột",
            _ => "✓ Đọc dữ liệu hiện tại\n✓ Xem chi tiết kết quả\n✓ Tải lại khi cần\n✓ Tìm trong báo cáo\n✓ Lưu thành file JSON"
        };
        await EnsureLoadedAsync(true);
    }

    private async void Reload_OnClick(object? sender, RoutedEventArgs e)
    {
        if (!_busy && await ConfirmDiscardDraftAsync()) { _loaded = false; await EnsureLoadedAsync(true); }
    }

    private async Task<bool> ConfirmDiscardDraftAsync()
    {
        if (!HasUnsavedChanges) return true;
        if (TopLevel.GetTopLevel(this) is not Window owner) return false;
        bool discard = false;
        var dialog = new Window { Title = "Bản nháp chưa áp dụng", Width = 510, Height = 195,
            CanResize = false, WindowStartupLocation = WindowStartupLocation.CenterOwner };
        var keep = new Button { [LocalizationService.TextProperty] = "Giữ bản nháp" };
        var replace = new Button { [LocalizationService.TextProperty] = "Bỏ thay đổi" };
        keep.Click += (_, _) => dialog.Close();
        replace.Click += (_, _) => { discard = true; dialog.Close(); };
        dialog.Content = new StackPanel { Margin = new Thickness(18), Spacing = 18, Children = {
            new TextBlock { [LocalizationService.TextProperty] = "Nội dung đang sửa sẽ bị thay thế. Bạn có thể giữ lại để lưu hoặc áp dụng trước.", TextWrapping = TextWrapping.Wrap },
            new StackPanel { Orientation = Orientation.Horizontal, Spacing = 12, Children = { keep, replace } }
        } };
        await dialog.ShowDialog(owner);
        return discard;
    }
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
        if (TopLevel.GetTopLevel(this) is Window window)
        {
            if (_expanded) { _previousWindowState=window.WindowState; window.WindowState=WindowState.FullScreen; }
            else window.WindowState=_previousWindowState;
        }
    }
    private void Tools_OnKeyDown(object? sender, KeyEventArgs e)
    {
        if (e.KeyModifiers == (KeyModifiers.Control | KeyModifiers.Shift) && e.Key == Key.F) Format_OnClick(sender, new RoutedEventArgs());
        else if (e.KeyModifiers == KeyModifiers.Control && e.Key == Key.F) Find_OnClick(sender, new RoutedEventArgs());
        else if (e.KeyModifiers == KeyModifiers.Control && e.Key == Key.S) Save_OnClick(sender, new RoutedEventArgs());
        else if (e.Key == Key.F11) Expand_OnClick(sender, new RoutedEventArgs());
        else return;
        e.Handled = true;
    }
    private async void Defaults_OnClick(object? sender, RoutedEventArgs e) => await RunAsync(async () =>
    {
        if (_supervisor is null || _mode is not ("editor" or "profile")) return;
        if (!await ConfirmDiscardDraftAsync()) return;
        ToolEditor.Text = JsonSerializer.Serialize(await _supervisor.GetDefaultConfigAsync(), Pretty);
        Result("Đã nạp mặc định vào bản nháp.", true);
        ToolResultDetail.Text = "Kiểm tra và nhấn Áp dụng nếu muốn thay cấu hình đang chạy.";
    });
    private void Help_OnClick(object? sender, RoutedEventArgs e)
    {
        Result("Mở hoặc chỉnh sửa JSON → kiểm tra cú pháp → áp dụng.", true);
        ToolResultDetail.Text = "Ctrl+F tìm kiếm • Ctrl+Shift+F định dạng • Ctrl+S lưu bản nháp ra file • F11 mở rộng. Áp dụng vào hệ thống thay đổi cấu hình đang chạy.";
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
    private async void TickHistoryStart_OnClick(object? sender,RoutedEventArgs e) => await RunAsync(async () =>
    {
        if(_supervisor is null)return;
        if(TickFromDate.SelectedDate is not {} from || TickToDate.SelectedDate is not {} to)
            throw new InvalidDataException("Chọn ngày bắt đầu và kết thúc để tải tick.");
        var response=await _supervisor.StartTickDownloadAsync(HistoryTerminal.Text ?? "",HistorySymbol.Text ?? "",from.ToString("yyyy-MM-dd"),to.ToString("yyyy-MM-dd"));
        EnsureOk(response);
        ToolEditor.Text=JsonSerializer.Serialize(response.GetProperty("history_download"),Pretty);
        Result("Đang tải tick và nến khởi tạo chỉ báo. Dữ liệu hoàn tất sẽ xuất hiện trong kho của Backtest/Tối ưu.",true);
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
            if (_supervisor is null) return;
            EnsureOk(await _supervisor.ValidateCalendarAsync(json.RootElement));
            Result("Lịch tin hợp lệ. Áp dụng để dùng trong phạm vi thời gian đã khai báo.",true);
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
        if (_supervisor is null) return;
        if (_mode == "news")
        {
            using var calendar=JsonDocument.Parse(ToolEditor.Text ?? "");
            EnsureOk(await _supervisor.ImportCalendarAsync(calendar.RootElement));
            _loadedText=ToolEditor.Text ?? "";
            Result("Đã lưu lịch tin và nối vào bộ lọc tin tức của cấu hình đang áp dụng.",true);
            return;
        }
        if (_mode is not ("editor" or "profile")) return;
        if (HasConflictingDraft?.Invoke() == true)
            throw new InvalidOperationException("Một tab khác có bản nháp chưa áp dụng. Hãy áp dụng hoặc hoàn tác bản nháp đó trước.");
        using var json = JsonDocument.Parse(ToolEditor.Text ?? "");
        var result = await _supervisor.ApplyActiveConfigAsync(json.RootElement, expectedProfile: _baselineProfile);
        if (result.Applied && result.Profile is { } applied)
        {
            _baselineProfile = applied.Clone();
            ToolEditor.Text = _loadedText = JsonSerializer.Serialize(applied, Pretty);
            ToolSymbol.Text = applied.GetProperty("strategy").GetProperty("symbol").GetString();
            ToolProfileName.Text = applied.GetProperty("profile").GetProperty("name").GetString();
        }
        Result(result.Applied ? "Đã áp dụng và lưu profile." : string.Join(" • ", result.Errors), result.Applied);
    });
    private async void Open_OnClick(object? sender, RoutedEventArgs e) => await RunAsync(async () =>
    {
        var top = TopLevel.GetTopLevel(this);
        if (top is null) return;
        if (!await ConfirmDiscardDraftAsync()) return;
        var paths = await top.StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions { Title = "Mở JSON", AllowMultiple = false, FileTypeFilter = new[] { JsonType } });
        if (paths.Count == 0) return;
        await using var stream = await paths[0].OpenReadAsync();
        if (stream.CanSeek && stream.Length > 2 * 1024 * 1024) throw new InvalidDataException("File vượt quá 2 MiB.");
        using var reader = new StreamReader(stream, Encoding.UTF8);
        var text = await reader.ReadToEndAsync();
        using var json = JsonDocument.Parse(text);
        ToolEditor.Text = JsonSerializer.Serialize(json.RootElement, Pretty);
        ToolFileName.Text = paths[0].Name;
        _currentFile=paths[0];
        if (_mode != "news") { _mode = "profile"; ToolEditor.IsReadOnly = false; ApplyToolButton.IsEnabled = SaveProfileButton.IsEnabled = DefaultProfileButton.IsEnabled = true; }
        Result("Đã mở file. Nhấn Kiểm tra cú pháp trước khi áp dụng.", true);
    });
    private void PresentReadOnlyReport(string mode, string json)
    {
        _mode=mode;
        _currentFile=null; // A report can never overwrite the previously opened profile.
        ToolFileName.Text=$"{mode}-report.json";
        ToolEditor.IsReadOnly=true;
        ApplyToolButton.IsEnabled=SaveProfileButton.IsEnabled=DefaultProfileButton.IsEnabled=false;
        ToolEditor.Text=_loadedText=json;
        _loaded=true;
        RefreshEditorInfo();
    }
    private async void Save_OnClick(object? sender, RoutedEventArgs e) => await RunAsync(async () =>
    {
        var top = TopLevel.GetTopLevel(this);
        if (top is null) return;
        var target=(sender as Button)?.Tag as string != "save-as" ? _currentFile : null;
        target ??= await top.StorageProvider.SaveFilePickerAsync(new FilePickerSaveOptions { Title = "Lưu JSON", SuggestedFileName = $"xaupy-{_mode}.json", DefaultExtension = "json", FileTypeChoices = new[] { JsonType } });
        if (target is null) return;
        using var json = JsonDocument.Parse(ToolEditor.Text ?? "");
        await FileOutput.WriteTextAsync(target,JsonSerializer.Serialize(json.RootElement,Pretty));
        _currentFile=target;
        ToolFileName.Text=target.Name;
        // Saving a draft does not apply it to the running strategy.
        Result($"Đã lưu {target.Name}.", true);
    });
    private async void CalculateRisk_OnClick(object? sender, RoutedEventArgs e)
    {
        try
        {
            double Number(TextBox box) => double.TryParse(box.Text, NumberStyles.Float, CultureInfo.InvariantCulture, out var n) && double.IsFinite(n) && n > 0 ? n : throw new InvalidDataException("Các giá trị phải là số dương.");
            var budget = Number(RiskBudget); var distance = Number(RiskDistance); var size = Number(RiskTickSize); var value = Number(RiskTickValue);
            if (_supervisor is null) return;
            var response=await _supervisor.QueryDiagnosticsAsync(); EnsureOk(response);
            var meta=response.GetProperty("diagnostics").GetProperty("broker_metadata");
            if (!meta.TryGetProperty("volume_step",out var stepValue)) throw new InvalidDataException("Cần kết nối MT5 để lấy bước lot và chi phí hiện tại.");
            var active=await _supervisor.GetActiveConfigAsync(); var costs=active.GetProperty("costs");
            double spread=meta.GetProperty("ask").GetDouble()-meta.GetProperty("bid").GetDouble();
            double slippage=costs.GetProperty("max_slippage_points").GetDouble()*meta.GetProperty("point").GetDouble();
            double commission=costs.GetProperty("max_commission_per_lot").GetDouble();
            double lossPerLot=(distance+spread+slippage)/size*value+commission;
            double step=stepValue.GetDouble(), minimum=meta.GetProperty("volume_min").GetDouble();
            double maximum=Math.Min(meta.GetProperty("volume_max").GetDouble(),active.GetProperty("risk").GetProperty("max_lot").GetDouble());
            if (step<=0 || maximum<minimum) throw new InvalidDataException("Thông số khối lượng broker chưa hợp lệ.");
            double lots=Math.Floor((Math.Min(budget/lossPerLot,maximum)+1e-10)/step)*step;
            if(lots<minimum) lots=0;
            ToolEditor.Text=JsonSerializer.Serialize(new {budget_usd=budget,sl_distance=distance,tick_size=size,tick_value_per_lot=value,
                spread_price=spread,slippage_price=slippage,commission_round_trip_per_lot=commission,risk_per_lot=lossPerLot,
                broker_volume_step=step,broker_volume_min=minimum,maximum_lot=maximum,lots=Math.Round(lots,8),estimated_loss=lots*lossPerLot,
                assumptions="Phí tối đa và trượt giá từ profile; chưa gồm swap giữ qua đêm. Không cấp quyền hoặc gửi lệnh."},Pretty);
            Result(lots>0 ? "Đã tính lot sau chi phí và làm tròn theo broker." : "Ngân sách không đủ cho lot tối thiểu của broker.",lots>0);
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
