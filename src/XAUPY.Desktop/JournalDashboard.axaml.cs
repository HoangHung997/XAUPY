using System.Text;
using System.Text.Json;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Platform.Storage;
using Avalonia.Threading;
using XAUPY.Ipc;

namespace XAUPY.Desktop;

public partial class JournalDashboard : UserControl
{
    private static readonly FilePickerFileType JsonLinesFileType = new("XAUPY Journal JSON Lines")
    {
        Patterns = new[] { "*.jsonl" }
    };

    private readonly DispatcherTimer _searchTimer;
    private readonly List<JournalEventSnapshot> _events = new();
    private EngineProcessSupervisor? _supervisor;
    private JournalSummarySnapshot _summary = JournalSummarySnapshot.Empty;
    private JournalEventSnapshot? _selectedEvent;
    private string _selectedSource = "ALL";
    private bool _bookmarksOnly;
    private bool _loading;
    private bool _initialized;
    private long _lastLoadedSequence = -1;

    public JournalDashboard()
    {
        InitializeComponent();

        _searchTimer = new DispatcherTimer
        {
            Interval = TimeSpan.FromMilliseconds(350)
        };
        _searchTimer.Tick += (_, _) =>
        {
            _searchTimer.Stop();
            _ = EnsureLoadedAsync(force: true);
        };

        _initialized = true;
        ApplySummary(JournalSummarySnapshot.Empty);
        RenderRows();
        RenderDetail(null);
    }

    public void AttachSupervisor(EngineProcessSupervisor supervisor)
    {
        _supervisor = supervisor;
    }

    public void ApplySummary(JournalSummarySnapshot summary)
    {
        _summary = summary;
        RenderSummary();

        if (!_initialized ||
            !IsVisible ||
            _loading ||
            summary.LatestSequence == _lastLoadedSequence)
        {
            return;
        }

        _ = EnsureLoadedAsync(force: true);
    }

    public async Task EnsureLoadedAsync(bool force = false)
    {
        if (!_initialized || _loading || _supervisor is null)
            return;

        if (_supervisor.State != EngineConnectionState.Ready)
        {
            SetStatus("Đang chờ Python Engine READY...", Brushes.Gold);
            return;
        }

        if (!force && _lastLoadedSequence == _summary.LatestSequence)
            return;

        var levels = SelectedLevels();
        if (levels.Count == 0)
        {
            _events.Clear();
            RenderRows();
            SetStatus("Không có mức log nào được chọn.", Brushes.Gold);
            return;
        }

        _loading = true;
        SetStatus("Đang tải journal thật từ Python Engine...", Brushes.LightBlue);

        try
        {
            IReadOnlyCollection<string>? sources =
                string.Equals(_selectedSource, "ALL", StringComparison.Ordinal)
                    ? null
                    : new[] { _selectedSource };

            var result = await _supervisor.QueryJournalAsync(
                levels,
                sources,
                Box("JournalSearchBox").Text,
                CurrentDateScope(),
                _bookmarksOnly,
                limit: 500);

            if (!result.Ok)
            {
                SetStatus(
                    result.Errors.Count > 0
                        ? string.Join(" • ", result.Errors)
                        : "Journal query bị từ chối.",
                    Brushes.IndianRed);
                return;
            }

            _events.Clear();
            _events.AddRange(result.Events);
            _summary = result.Summary;
            _lastLoadedSequence = result.LatestSequence;

            if (_selectedEvent is not null)
            {
                _selectedEvent = _events.FirstOrDefault(
                    item => item.Sequence == _selectedEvent.Sequence)
                    ?? _summary.Bookmarks.FirstOrDefault(
                        item => item.Sequence == _selectedEvent.Sequence)
                    ?? _summary.RecentAlerts.FirstOrDefault(
                        item => item.Sequence == _selectedEvent.Sequence);
            }

            RenderRows();
            RenderSummary();
            RenderDetail(_selectedEvent);
            SetStatus(
                $"{result.TotalMatched} bản ghi phù hợp • hiển thị {_events.Count} dòng • latest #{result.LatestSequence}",
                Brushes.LightGreen);
        }
        catch (Exception ex)
        {
            SetStatus($"Không tải được journal: {ex.Message}", Brushes.IndianRed);
        }
        finally
        {
            _loading = false;
        }
    }

    private void SourceFilter_OnClick(object? sender, RoutedEventArgs e)
    {
        if (sender is not Button { Tag: string source })
            return;

        _selectedSource = source;
        _bookmarksOnly = false;
        UpdateSourceButtonClasses();
        UpdateBookmarkFilterButton();
        _ = EnsureLoadedAsync(force: true);
    }

    private void LevelFilter_OnClick(object? sender, RoutedEventArgs e)
    {
        if (_initialized)
            _ = EnsureLoadedAsync(force: true);
    }

    private void JournalSearchBox_OnTextChanged(object? sender, TextChangedEventArgs e)
    {
        if (!_initialized)
            return;

        _searchTimer.Stop();
        _searchTimer.Start();
    }

    private void DateScope_OnSelectionChanged(object? sender, SelectionChangedEventArgs e)
    {
        if (_initialized)
            _ = EnsureLoadedAsync(force: true);
    }

    private void BookmarksOnly_OnClick(object? sender, RoutedEventArgs e)
    {
        _bookmarksOnly = !_bookmarksOnly;
        UpdateBookmarkFilterButton();
        _ = EnsureLoadedAsync(force: true);
    }

    private void Refresh_OnClick(object? sender, RoutedEventArgs e) =>
        _ = EnsureLoadedAsync(force: true);

    private void ShowAlerts_OnClick(object? sender, RoutedEventArgs e)
    {
        _selectedSource = "Alerts";
        _bookmarksOnly = false;
        UpdateSourceButtonClasses();
        UpdateBookmarkFilterButton();
        _ = EnsureLoadedAsync(force: true);
    }

    private void ShowBookmarks_OnClick(object? sender, RoutedEventArgs e)
    {
        _selectedSource = "ALL";
        _bookmarksOnly = true;
        UpdateSourceButtonClasses();
        UpdateBookmarkFilterButton();
        _ = EnsureLoadedAsync(force: true);
    }

    private async void ToggleSelectedBookmark_OnClick(object? sender, RoutedEventArgs e)
    {
        if (_selectedEvent is null)
        {
            SetStatus("Hãy chọn một dòng journal trước khi thêm dấu trang.", Brushes.Gold);
            return;
        }

        if (_supervisor is null || _supervisor.State != EngineConnectionState.Ready)
        {
            SetStatus("Python Engine chưa READY.", Brushes.Gold);
            return;
        }

        try
        {
            bool target = !_selectedEvent.Bookmarked;
            var result = await _supervisor.SetJournalBookmarkAsync(
                _selectedEvent.Sequence,
                target);

            if (!result.Ok || result.Event is null)
            {
                SetStatus(
                    result.Errors.Count > 0
                        ? string.Join(" • ", result.Errors)
                        : "Không cập nhật được dấu trang.",
                    Brushes.IndianRed);
                return;
            }

            _selectedEvent = result.Event;
            _summary = result.Summary;
            RenderSummary();
            RenderDetail(_selectedEvent);
            await EnsureLoadedAsync(force: true);
            SetStatus(
                target ? "Đã thêm dấu trang." : "Đã bỏ dấu trang.",
                Brushes.LightGreen);
        }
        catch (Exception ex)
        {
            SetStatus($"Bookmark lỗi: {ex.Message}", Brushes.IndianRed);
        }
    }

    private void JournalRow_OnClick(object? sender, RoutedEventArgs e)
    {
        if (sender is not Button { Tag: long sequence })
            return;

        _selectedEvent = _events.FirstOrDefault(
            item => item.Sequence == sequence);
        RenderRows();
        RenderDetail(_selectedEvent);
    }

    private void SideEvent_OnClick(object? sender, RoutedEventArgs e)
    {
        if (sender is not Button { Tag: long sequence })
            return;

        _selectedEvent =
            _summary.RecentAlerts.FirstOrDefault(item => item.Sequence == sequence)
            ?? _summary.Bookmarks.FirstOrDefault(item => item.Sequence == sequence)
            ?? _events.FirstOrDefault(item => item.Sequence == sequence);

        RenderRows();
        RenderDetail(_selectedEvent);
    }

    private async void ExportLog_OnClick(object? sender, RoutedEventArgs e)
    {
        if (_events.Count == 0)
        {
            SetStatus("Không có bản ghi đang lọc để xuất.", Brushes.Gold);
            return;
        }

        var top = TopLevel.GetTopLevel(this);
        if (top?.StorageProvider is null || !top.StorageProvider.CanSave)
        {
            SetStatus("Storage provider không hỗ trợ lưu file.", Brushes.IndianRed);
            return;
        }

        var file = await top.StorageProvider.SaveFilePickerAsync(
            new FilePickerSaveOptions
            {
                Title = "Xuất XAUPY Journal",
                SuggestedFileName = $"XAUPY-Journal-{DateTime.Now:yyyyMMdd-HHmmss}.jsonl",
                DefaultExtension = "jsonl",
                FileTypeChoices = new[] { JsonLinesFileType }
            });

        if (file is null)
            return;

        try
        {
            await using var stream = await file.OpenWriteAsync();
            if (stream.CanSeek)
                stream.SetLength(0);

            await using var writer = new StreamWriter(
                stream,
                new UTF8Encoding(encoderShouldEmitUTF8Identifier: false),
                leaveOpen: true);

            foreach (var item in _events.OrderBy(item => item.Sequence))
            {
                var record = new
                {
                    schema_version = 1,
                    sequence = item.Sequence,
                    event_id = item.EventId,
                    timestamp_utc = item.TimestampUtc,
                    level = item.Level,
                    source = item.Source,
                    tag = item.Tag,
                    message = item.Message,
                    details = item.Details,
                    correlation_id = item.CorrelationId,
                    symbol = item.Symbol,
                    profile_hash = item.ProfileHash,
                    bookmarked = item.Bookmarked
                };
                await writer.WriteLineAsync(JsonSerializer.Serialize(record));
            }

            await writer.FlushAsync();
            await stream.FlushAsync();
            SetStatus(
                $"Đã xuất {_events.Count} dòng journal: {file.Name}",
                Brushes.LightGreen);
        }
        catch (Exception ex)
        {
            SetStatus($"Xuất journal lỗi: {ex.Message}", Brushes.IndianRed);
        }
    }

    private void RenderRows()
    {
        var host = Panel("JournalRowsHost");
        host.Children.Clear();

        if (_events.Count == 0)
        {
            host.Children.Add(
                new Border
                {
                    Background = new SolidColorBrush(Color.Parse("#06192C")),
                    Padding = new Thickness(14, 18),
                    Child = new TextBlock
                    {
                        Text = "Không có bản ghi phù hợp với bộ lọc hiện tại.",
                        Foreground = new SolidColorBrush(Color.Parse("#8099B2")),
                        HorizontalAlignment = HorizontalAlignment.Center
                    }
                });
            return;
        }

        foreach (var item in _events)
            host.Children.Add(CreateJournalRow(item));
    }

    private Button CreateJournalRow(JournalEventSnapshot item)
    {
        var grid = new Grid
        {
            ColumnDefinitions = new ColumnDefinitions("64,160,110,150,*,135"),
            MinHeight = 34
        };

        AddCell(grid, 0, item.Sequence.ToString(), Brushes.LightGray);
        AddCell(grid, 1, LocalTime(item.TimestampUtc), Brushes.LightGray);
        AddCell(grid, 2, $"{LevelIcon(item.Level)}  {item.Level}", LevelBrush(item.Level));
        AddCell(grid, 3, item.Source, SourceBrush(item.Source));
        AddCell(grid, 4, item.Message, Brushes.White);
        AddCell(grid, 5, item.Tag, new SolidColorBrush(Color.Parse("#A9C3DD")));

        var button = new Button
        {
            Tag = item.Sequence,
            Classes = { "journalRow" },
            Content = grid
        };
        if (_selectedEvent?.Sequence == item.Sequence)
            button.Classes.Add("selectedRow");

        button.Click += JournalRow_OnClick;

        return button;
    }

    private void RenderSummary()
    {
        Text("SourceAllCountText").Text = _summary.Total.ToString();
        Text("SourceMt5CountText").Text = SourceCount("MT5").ToString();
        Text("SourceBridgeCountText").Text = SourceCount("EA Bridge").ToString();
        Text("SourcePythonCountText").Text = SourceCount("Python Engine").ToString();
        Text("SourceStrategyCountText").Text = SourceCount("Strategy").ToString();
        Text("SourceOrdersCountText").Text = SourceCount("Orders").ToString();
        Text("SourceAlertsCountText").Text = SourceCount("Alerts").ToString();

        Text("InfoCountText").Text = LevelCount("INFO").ToString();
        Text("WarnCountText").Text = LevelCount("WARN").ToString();
        Text("ErrorCountText").Text = LevelCount("ERROR").ToString();
        Text("DebugCountText").Text = LevelCount("DEBUG").ToString();

        Text("ReplayIntegrityText").Text =
            $"Invalid: {_summary.InvalidReplayLines} • Duplicate: {_summary.DuplicateReplayLines}";

        RenderSideEvents(
            Panel("RecentAlertsHost"),
            _summary.RecentAlerts,
            emptyMessage: "Chưa có cảnh báo gần đây.");

        RenderSideEvents(
            Panel("BookmarksHost"),
            _summary.Bookmarks,
            emptyMessage: "Chưa có dấu trang.");

        UpdateSourceButtonClasses();
        UpdateBookmarkFilterButton();
    }

    private void RenderSideEvents(
        StackPanel host,
        IReadOnlyList<JournalEventSnapshot> items,
        string emptyMessage)
    {
        host.Children.Clear();

        if (items.Count == 0)
        {
            host.Children.Add(
                new TextBlock
                {
                    Text = emptyMessage,
                    Foreground = new SolidColorBrush(Color.Parse("#8099B2")),
                    FontSize = 11,
                    Margin = new Thickness(4, 8)
                });
            return;
        }

        foreach (var item in items.Take(5))
        {
            var grid = new Grid
            {
                ColumnDefinitions = new ColumnDefinitions("72,70,*"),
                Margin = new Thickness(4, 2)
            };
            AddCell(grid, 0, LocalClock(item.TimestampUtc), Brushes.LightGray);
            AddCell(grid, 1, item.Level, LevelBrush(item.Level));
            AddCell(grid, 2, item.Message, Brushes.White);

            var button = new Button
            {
                Tag = item.Sequence,
                Classes = { "journalRow" },
                Content = grid
            };
            button.Click += SideEvent_OnClick;
            host.Children.Add(button);
        }
    }

    private void RenderDetail(JournalEventSnapshot? item)
    {
        if (item is null)
        {
            Text("DetailTimeText").Text = "—";
            Text("DetailLevelText").Text = "—";
            Text("DetailLevelText").Foreground = Brushes.LightGray;
            Text("DetailSourceText").Text = "—";
            Text("DetailTagText").Text = "—";
            Text("DetailSequenceText").Text = "—";
            Text("DetailMessageText").Text = "Chọn một dòng để xem chi tiết.";
            Text("DetailJsonText").Text = "—";
            Text("DetailBookmarkText").Text = "Chưa chọn dòng";
            return;
        }

        Text("DetailTimeText").Text = LocalTime(item.TimestampUtc);
        Text("DetailLevelText").Text = item.Level;
        Text("DetailLevelText").Foreground = LevelBrush(item.Level);
        Text("DetailSourceText").Text = item.Source;
        Text("DetailTagText").Text = item.Tag;
        Text("DetailSequenceText").Text = item.Sequence.ToString();
        Text("DetailMessageText").Text = item.Message;
        Text("DetailBookmarkText").Text =
            item.Bookmarked ? "🔖 Đã đánh dấu" : "Chưa đánh dấu";

        var detail = new
        {
            event_id = item.EventId,
            correlation_id = item.CorrelationId,
            symbol = item.Symbol,
            profile_hash = item.ProfileHash,
            details = item.Details
        };
        Text("DetailJsonText").Text = JsonSerializer.Serialize(
            detail,
            new JsonSerializerOptions { WriteIndented = true });
    }

    private IReadOnlyCollection<string> SelectedLevels()
    {
        var values = new List<string>();
        if (Check("InfoLevelCheck").IsChecked == true) values.Add("INFO");
        if (Check("WarnLevelCheck").IsChecked == true) values.Add("WARN");
        if (Check("ErrorLevelCheck").IsChecked == true) values.Add("ERROR");
        if (Check("DebugLevelCheck").IsChecked == true) values.Add("DEBUG");
        return values;
    }

    private string CurrentDateScope()
    {
        var combo = this.FindControl<ComboBox>("DateScopeCombo");
        if (combo?.SelectedItem is ComboBoxItem { Tag: string tag })
            return tag;
        return "TODAY";
    }

    private void UpdateSourceButtonClasses()
    {
        foreach (var (name, source) in new[]
        {
            ("SourceAllButton", "ALL"),
            ("SourceMt5Button", "MT5"),
            ("SourceBridgeButton", "EA Bridge"),
            ("SourcePythonButton", "Python Engine"),
            ("SourceStrategyButton", "Strategy"),
            ("SourceOrdersButton", "Orders"),
            ("SourceAlertsButton", "Alerts"),
        })
        {
            var button = Button(name);
            bool active = string.Equals(
                source,
                _selectedSource,
                StringComparison.Ordinal);
            bool hasClass = button.Classes.Contains("activeSource");

            if (active && !hasClass)
                button.Classes.Add("activeSource");
            else if (!active && hasClass)
                button.Classes.Remove("activeSource");
        }
    }

    private void UpdateBookmarkFilterButton()
    {
        var button = Button("BookmarksOnlyButton");
        button.Content = _bookmarksOnly
            ? "🔖  Đang lọc dấu trang"
            : "🔖  Dấu trang";
        button.Foreground = _bookmarksOnly ? Brushes.Gold : Brushes.White;
    }

    private int LevelCount(string level) =>
        _summary.LevelCounts.TryGetValue(level, out var value) ? value : 0;

    private int SourceCount(string source) =>
        _summary.SourceCounts.TryGetValue(source, out var value) ? value : 0;

    private void SetStatus(string value, IBrush brush)
    {
        Text("JournalStatusText").Text = value;
        Text("JournalStatusText").Foreground = brush;
    }

    private static void AddCell(
        Grid grid,
        int column,
        string value,
        IBrush brush)
    {
        var text = new TextBlock
        {
            Text = value,
            Foreground = brush,
            FontSize = 11,
            VerticalAlignment = VerticalAlignment.Center,
            Margin = new Thickness(10, 5),
            TextTrimming = TextTrimming.CharacterEllipsis
        };
        Grid.SetColumn(text, column);
        grid.Children.Add(text);
    }

    private static IBrush LevelBrush(string level) => level switch
    {
        "INFO" => Brushes.DeepSkyBlue,
        "WARN" => Brushes.Gold,
        "ERROR" => Brushes.IndianRed,
        "DEBUG" => Brushes.LightSkyBlue,
        _ => Brushes.LightGray
    };

    private static IBrush SourceBrush(string source) => source switch
    {
        "MT5" => Brushes.LightGreen,
        "EA Bridge" => Brushes.LightSkyBlue,
        "Python Engine" => Brushes.Gold,
        "Strategy" => Brushes.MediumSpringGreen,
        "Orders" => Brushes.LightBlue,
        "Alerts" => Brushes.IndianRed,
        _ => Brushes.LightGray
    };

    private static string LevelIcon(string level) => level switch
    {
        "INFO" => "●",
        "WARN" => "▲",
        "ERROR" => "×",
        "DEBUG" => "⚙",
        _ => "•"
    };

    private static string LocalTime(string raw)
    {
        if (!DateTimeOffset.TryParse(raw, out var value))
            return raw;
        return value.ToLocalTime().ToString("yyyy.MM.dd HH:mm:ss");
    }

    private static string LocalClock(string raw)
    {
        if (!DateTimeOffset.TryParse(raw, out var value))
            return raw;
        return value.ToLocalTime().ToString("HH:mm:ss");
    }

    private TextBlock Text(string name) =>
        this.FindControl<TextBlock>(name)
        ?? throw new InvalidOperationException($"Missing Journal TextBlock: {name}");

    private TextBox Box(string name) =>
        this.FindControl<TextBox>(name)
        ?? throw new InvalidOperationException($"Missing Journal TextBox: {name}");

    private CheckBox Check(string name) =>
        this.FindControl<CheckBox>(name)
        ?? throw new InvalidOperationException($"Missing Journal CheckBox: {name}");

    private Button Button(string name) =>
        this.FindControl<Button>(name)
        ?? throw new InvalidOperationException($"Missing Journal Button: {name}");

    private StackPanel Panel(string name) =>
        this.FindControl<StackPanel>(name)
        ?? throw new InvalidOperationException($"Missing Journal panel: {name}");
}
