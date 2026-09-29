using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Platform.Storage;
using System.Diagnostics;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using XAUPY.Ipc;

namespace XAUPY.Desktop;

public partial class ConfigurationEditor : UserControl
{
    private sealed record FieldDescriptor(
        string Path,
        string Kind,
        string SetKey,
        string Description,
        IReadOnlyList<string> EnumValues,
        double? Minimum,
        double? Maximum,
        JsonNode? LockedValue);

    private sealed class FieldBinding
    {
        public required FieldDescriptor Descriptor { get; init; }
        public required Border Row { get; init; }
        public required Control Editor { get; init; }
        public required string GroupKey { get; init; }
    }

    private sealed class GroupBinding
    {
        public required Border Card { get; init; }
        public required List<FieldBinding> Fields { get; init; }
    }

    private static readonly IReadOnlyDictionary<string, (int Order, string Title)> GroupTitles =
        new Dictionary<string, (int, string)>(StringComparer.Ordinal)
        {
            ["profile"] = (11, "11. Hồ sơ cấu hình"),
            ["strategy"] = (12, "12. Quyền giao dịch"),
            ["timeframes"] = (5, "5. Khung thời gian (Timeframe)"),
            ["mtf"] = (6, "Xác nhận đa khung thời gian bổ sung"),
            ["direction"] = (2, "2. Hướng giao dịch"),
            ["pullback"] = (3, "3. Nhận diện nhịp hồi (Pullback)"),
            ["trigger"] = (4, "4. Xác nhận vào lệnh (Trigger)"),
            ["filters.adx"] = (15, "07. ADX"),
            ["filters.atr"] = (16, "08. ATR"),
            ["filters.open"] = (17, "09. Open Filter"),
            ["entry"] = (18, "10. Entry"),
            ["risk"] = (1, "1. Khởi tạo & an toàn"),
            ["stop_loss"] = (6, "6. Stop loss (SL)"),
            ["take_profit"] = (7, "7. Take profit (TP)"),
            ["take_profit.dynamic"] = (14, "14. Dynamic TP"),
            ["management"] = (8, "8. Quản lý sau vào"),
            ["sessions"] = (9, "9. Phiên giao dịch"),
            ["news"] = (10, "10. Lọc tin tức"),
            ["costs"] = (18, "18. Cost Filters"),
            ["execution"] = (19, "19. Execution Identity"),
            ["safety"] = (20, "20. Hard Safety"),
            ["logging"] = (21, "21. Logging"),
        };

    private static readonly FilePickerFileType JsonFileType = new("XAUPY profile JSON")
    {
        Patterns = new[] { "*.json" }
    };

    private static readonly FilePickerFileType SetFileType = new("MetaTrader 5 preset")
    {
        Patterns = new[] { "*.set" }
    };

    private readonly List<FieldBinding> _fields = new();
    private readonly Dictionary<string, GroupBinding> _groups = new(StringComparer.Ordinal);

    private EngineProcessSupervisor? _supervisor;
    private JsonObject? _draft;
    private bool _schemaLoaded;
    private bool _loading;
    private bool _suppressChanges;
    private bool _dirty;
    private Task? _loadTask;
    public bool HasUnsavedChanges => _dirty;
    public Func<bool>? HasConflictingDraft { get; set; }
    private EngineConnectionState _lastEngineState = EngineConnectionState.Stopped;
    private string? _lastSetTemplatePath;
    private IStorageFile? _currentJsonFile;

    public ConfigurationEditor()
    {
        InitializeComponent();
    }

    public void AttachSupervisor(EngineProcessSupervisor supervisor)
    {
        _supervisor = supervisor;
    }

    public async Task OpenShortcutAsync(string action)
    {
        await EnsureLoadedAsync();
        if (!_schemaLoaded) return;
        switch (action)
        {
            case "save": SaveJson_OnClick(this, new RoutedEventArgs()); break;
            case "load": LoadJson_OnClick(this, new RoutedEventArgs()); break;
            case "import-set": ImportSet_OnClick(this, new RoutedEventArgs()); break;
            case "export-set": ExportSet_OnClick(this, new RoutedEventArgs()); break;
            default:
                this.FindControl<TextBox>("SearchBox")!.Text = string.Empty;
                if (_groups.TryGetValue(action, out var group)) group.Card.BringIntoView();
                break;
        }
    }

    public async Task NotifyEngineStateAsync(EngineConnectionState state)
    {
        bool becameReady = state == EngineConnectionState.Ready &&
                           _lastEngineState != EngineConnectionState.Ready;
        _lastEngineState = state;

        if (becameReady)
        {
            _schemaLoaded = false;
            await EnsureLoadedAsync(force: true);
            return;
        }

        if (state != EngineConnectionState.Ready && !_loading)
        {
            SetStatus("Python Engine chưa READY. Editor giữ draft hiện tại và sẽ đồng bộ lại khi Engine kết nối.", Brushes.Gold);
        }
    }

    public Task EnsureLoadedAsync(bool force = false)
    {
        if (_loadTask is { IsCompleted: false }) return _loadTask;
        return _loadTask = LoadAsync(force);
    }

    private async Task LoadAsync(bool force)
    {
        if (_loading || _supervisor is null)
            return;

        if (_schemaLoaded && !force)
            return;

        if (_supervisor.State != EngineConnectionState.Ready)
        {
            SetStatus("Đang chờ Python Engine READY...", Brushes.Gold);
            return;
        }

        _loading = true;

        try
        {
            SetStatus(LocalizationService.T("Đang tải tham số và cấu hình đang dùng…"), Brushes.LightBlue);

            var schema = await _supervisor.GetConfigSchemaAsync();
            var active = await _supervisor.GetActiveConfigAsync();

            // A reconnect or a shared asynchronous load must not replace edits
            // made before or while the requests were in flight. Capture the
            // current draft immediately before rebuilding its schema controls.
            bool keepDraft = _dirty && _draft is not null;
            var profile = keepDraft ? JsonSerializer.SerializeToElement(_draft) : active;
            BuildSchema(schema);
            LoadDraft(profile, dirty: keepDraft);

            _schemaLoaded = true;
            if (keepDraft)
                SetStatus("Engine đã kết nối lại. Bản nháp chưa áp dụng được giữ nguyên; Python sẽ xác thực lại khi bấm Áp dụng.", Brushes.Gold);
            else
                SetStatus("Đã tải active profile. Tất cả tham số canonical đang sẵn sàng chỉnh sửa.", Brushes.LightGreen);
        }
        catch (Exception ex)
        {
            SetStatus($"Không tải được cấu hình: {ex.Message}", Brushes.IndianRed);
        }
        finally
        {
            _loading = false;
        }
    }

    private void BuildSchema(JsonElement schema)
    {
        if (!schema.TryGetProperty("fields", out var fieldsElement) ||
            fieldsElement.ValueKind != JsonValueKind.Array)
        {
            throw new InvalidDataException("Config schema is missing fields.");
        }

        var descriptors = new List<FieldDescriptor>();

        foreach (var field in fieldsElement.EnumerateArray())
        {
            string path = ReadRequiredString(field, "path");
            string kind = ReadRequiredString(field, "kind");
            string setKey = ReadRequiredString(field, "set_key");
            string description = ReadOptionalString(field, "description") ?? string.Empty;

            var enumValues = new List<string>();
            if (field.TryGetProperty("enum", out var enumElement) &&
                enumElement.ValueKind == JsonValueKind.Array)
            {
                foreach (var item in enumElement.EnumerateArray())
                {
                    if (item.ValueKind == JsonValueKind.String && item.GetString() is { } value)
                        enumValues.Add(value);
                }
            }

            double? minimum = TryReadNullableDouble(field, "minimum");
            double? maximum = TryReadNullableDouble(field, "maximum");

            JsonNode? lockedValue = null;
            if (field.TryGetProperty("locked_value", out var lockedElement) &&
                lockedElement.ValueKind != JsonValueKind.Null &&
                lockedElement.ValueKind != JsonValueKind.Undefined)
            {
                lockedValue = JsonNode.Parse(lockedElement.GetRawText());
            }

            descriptors.Add(new FieldDescriptor(
                path,
                kind,
                setKey,
                description,
                enumValues,
                minimum,
                maximum,
                lockedValue));
        }

        _fields.Clear();
        _groups.Clear();

        var host = this.FindControl<Grid>("FieldsHost")
            ?? throw new InvalidOperationException("FieldsHost missing.");
        var validationCard = this.FindControl<Border>("ValidationCard")!;
        host.Children.Clear();
        host.RowDefinitions.Clear();
        foreach (var height in new[] { 156d, 188d, 144d, 176d })
            host.RowDefinitions.Add(new RowDefinition(new GridLength(height)));
        var remaining = descriptors.ToDictionary(d => d.Path, StringComparer.Ordinal);
        void AddCard(string key, string titleText, string[] paths, int row, int column, int span, int columns = 2)
        {
            var values = paths.Where(remaining.ContainsKey).Select(path => remaining[path]).ToArray();
            foreach (var field in values) remaining.Remove(field.Path);
            var groupFields = new List<FieldBinding>();
            var content = new Grid { RowDefinitions = new RowDefinitions("31,*") };
            var title = new TextBlock { [LocalizationService.TextProperty] = titleText, [AppearanceService.BaseFontSizeProperty] = span <= 2 ? 13d : 15d, FontWeight = FontWeight.SemiBold,
                Foreground = new SolidColorBrush(Color.Parse("#C5DEFA")), Margin = new Avalonia.Thickness(10, 5) };
            content.Children.Add(new Border { Background = new SolidColorBrush(Color.Parse("#082038")),
                BorderBrush = new SolidColorBrush(Color.Parse("#14517A")), BorderThickness = new Avalonia.Thickness(0,0,0,1), Child = title });
            var fieldsGrid = new Grid { ColumnDefinitions = new ColumnDefinitions(columns == 2 ? "*,*" : "*"),
                ColumnSpacing = 18, RowSpacing = span <= 4 ? 1 : 3, Margin = new Avalonia.Thickness(10,4) };
            Grid.SetRow(fieldsGrid, 1);
            int rows = (values.Length + columns - 1) / columns;
            for (int i = 0; i < rows; i++) fieldsGrid.RowDefinitions.Add(new RowDefinition(GridLength.Auto));
            if (columns == 2 && rows > 0)
            {
                var divider = new Border { Width = 1, Background = new SolidColorBrush(Color.Parse("#14517A")),
                    HorizontalAlignment = HorizontalAlignment.Right, Margin = new Avalonia.Thickness(0, 1, -9, 1) };
                Grid.SetRowSpan(divider, rows);
                fieldsGrid.Children.Add(divider);
            }
            for (int i = 0; i < values.Length; i++)
            {
                var binding = CreateFieldRow(values[i], key);
                groupFields.Add(binding); _fields.Add(binding);
                Grid.SetColumn(binding.Row, i / rows); Grid.SetRow(binding.Row, i % rows);
                if (key == "timeframes" && binding.Row.Child is Grid fieldGrid && binding.Editor is ComboBox combo)
                {
                    fieldGrid.ColumnDefinitions = new ColumnDefinitions("190,125,*");
                    var chips = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 4, Margin = new Avalonia.Thickness(8,0,0,0) };
                    foreach (var tf in values[i].EnumValues)
                    {
                        var chip = new Button { Content = tf, Padding = new Avalonia.Thickness(5,2), [AppearanceService.BaseFontSizeProperty] = 11d,
                            MinWidth = 34, Height = 25, Classes = { "secondary" }, Tag = tf };
                        chip.Click += (_, _) => combo.SelectedItem = tf;
                        combo.SelectionChanged += (_, _) => chip.Background = new SolidColorBrush(Color.Parse(combo.SelectedItem?.ToString() == tf ? "#0866F4" : "#0A2946"));
                        chips.Children.Add(chip);
                    }
                    Grid.SetColumn(chips, 2); fieldGrid.Children.Add(chips);
                }
                fieldsGrid.Children.Add(binding.Row);
            }
            content.Children.Add(fieldsGrid);
            var card = new Border { Classes = { "panel" }, Child = content };
            Grid.SetColumn(card,column); Grid.SetColumnSpan(card,span); Grid.SetRow(card,row); host.Children.Add(card);
            _groups[key] = new GroupBinding { Card = card, Fields = groupFields };
        }
        AddCard("risk", "⬡  1. Khởi tạo & an toàn", ["risk.risk_percent","risk.fixed_lot","risk.max_lot","risk.max_daily_loss_pct","risk.max_open_positions","risk.max_trades_per_day","risk.cooldown_minutes","risk.max_consecutive_losses"], 0,0,6);
        AddCard("direction", "⇄  2. Hướng giao dịch", ["strategy.allow_buy","strategy.allow_sell","direction.ma_type","direction.ma_period","direction.ma_enabled","direction.require_close_side","direction.open_filter_enabled","direction.price_source"], 0,6,6);
        AddCard("pullback", "⌁  3. Nhận diện nhịp hồi (Pullback)", descriptors.Where(d => GroupKey(d.Path) == "pullback").Select(d => d.Path).ToArray(), 1,0,6);
        AddCard("trigger", "◎  4. Xác nhận vào lệnh (Trigger)", descriptors.Where(d => GroupKey(d.Path) == "trigger").Select(d => d.Path).ToArray(), 1,6,6);
        AddCard("timeframes", "▥  5. Khung thời gian (Timeframe)", ["timeframes.direction","timeframes.pullback","timeframes.trigger"], 2,0,8,1);
        AddCard("sessions", "◷  9. Phiên giao dịch", ["sessions.session1_enabled","sessions.session1_start","sessions.session1_end","sessions.session2_enabled","sessions.session2_start","sessions.session2_end"], 2,8,4);
        AddCard("stop_loss", "⬡  6. Stop loss (SL)", ["stop_loss.mode","stop_loss.atr_period","stop_loss.atr_multiplier","stop_loss.min_price_units","stop_loss.max_price_units"], 3,0,2,1);
        AddCard("take_profit", "◎  7. Take profit (TP)", ["take_profit.mode","take_profit.rr_ratio","take_profit.fixed_price_units","take_profit.dynamic.near_tp_distance","take_profit.dynamic.max_extension_price_units"], 3,2,2,1);
        AddCard("management", "⚙  8. Quản lý sau vào", ["management.breakeven_enabled","management.breakeven_trigger_rr","management.partial_close_enabled","management.partial_close_percent","management.trailing_enabled"], 3,4,2,1);
        AddCard("news", "▤  10. Lọc tin tức", ["news.minutes_before","news.minutes_after","news.high_impact_only","news.enabled"], 3,6,2,1);
        host.Children.Add(validationCard);
        int advancedIndex = 0;
        foreach (var grouping in remaining.Values.ToArray().GroupBy(d => GroupKey(d.Path)).OrderBy(g => GroupTitle(g.Key).Order))
        {
            int row = 4 + advancedIndex / 2;
            if (advancedIndex % 2 == 0) host.RowDefinitions.Add(new RowDefinition(GridLength.Auto));
            var key = _groups.ContainsKey(grouping.Key) ? grouping.Key + ".more" : grouping.Key;
            AddCard(key, "Tham số bổ sung • " + GroupTitle(grouping.Key).Title, grouping.Select(d => d.Path).ToArray(), row, (advancedIndex % 2) * 6, 6);
            advancedIndex++;
        }

        var declaredCount = schema.TryGetProperty("field_count", out var countElement) &&
                            countElement.TryGetInt32(out var count)
            ? count
            : _fields.Count;

        if (declaredCount != _fields.Count)
            throw new InvalidDataException($"Schema field_count={declaredCount} but UI built {_fields.Count} rows.");

        this.FindControl<TextBlock>("FieldCountText")!.Text = $"{_fields.Count} tham số";
        ApplySearchFilter();
    }

    private FieldBinding CreateFieldRow(FieldDescriptor descriptor, string groupKey)
    {
        var rowContent = new Grid
        {
            ColumnDefinitions = new ColumnDefinitions(groupKey is "stop_loss" or "take_profit" or "management" or "news" ? "1.05*,1*" : "1.35*,1*"),
            ColumnSpacing = 6,
            MinHeight = 25
        };
        var label = new TextBlock
        {
            [LocalizationService.TextProperty] = FieldLabel(descriptor),
            [AppearanceService.BaseFontSizeProperty] = groupKey is "stop_loss" or "take_profit" or "management" or "news" ? 13d : 14d,
            Foreground = new SolidColorBrush(Color.Parse("#C0D5EB")),
            TextTrimming = TextTrimming.CharacterEllipsis,
            VerticalAlignment = VerticalAlignment.Center
        };
        ToolTip.SetTip(label, $"{descriptor.Path}\n{descriptor.Description}\n{descriptor.SetKey}\n{BoundsText(descriptor)}");
        rowContent.Children.Add(label);
        Control editor = CreateEditor(descriptor);
        editor.MinHeight = 25;
        editor.Height = 25;
        if (editor is Avalonia.Controls.Primitives.TemplatedControl input) { input.SetValue(AppearanceService.BaseFontSizeProperty, groupKey is "stop_loss" or "take_profit" or "management" or "news" ? 12d : 13d); input.Padding = new Avalonia.Thickness(6,2); }
        editor.VerticalAlignment = VerticalAlignment.Center;
        editor.HorizontalAlignment = HorizontalAlignment.Stretch;
        Grid.SetColumn(editor, 1);
        rowContent.Children.Add(editor);
        if (descriptor.LockedValue is not null)
        {
            editor.IsEnabled = false;
            ToolTip.SetTip(editor, $"Khóa an toàn: {descriptor.LockedValue}");
        }
        var row = new Border
        {
            BorderBrush = new SolidColorBrush(Color.Parse("#123047")),
            BorderThickness = new Avalonia.Thickness(0, 0, 0, .5),
            Child = rowContent
        };

        return new FieldBinding
        {
            Descriptor = descriptor,
            Row = row,
            Editor = editor,
            GroupKey = groupKey
        };
    }

    private void Category_OnClick(object? sender, RoutedEventArgs e)
    {
        if (sender is not Button { Tag: string key } || !_groups.TryGetValue(key, out var group)) return;
        this.FindControl<TextBox>("SearchBox")!.Text = string.Empty;
        group.Card.BringIntoView();
    }

    private static string FieldLabel(FieldDescriptor field)
    {
        if (FieldLabels.TryGetValue(field.Path, out var translated)) return translated;
        if (!string.IsNullOrWhiteSpace(field.Description)) return field.Description;
        return field.Path.Split('.').Last().Replace('_', ' ');
    }

    private static readonly IReadOnlyDictionary<string, string> FieldLabels = new Dictionary<string, string>
    {
        ["mtf.pullback_timeframes"] = "Pullback bổ sung (VD: M3,M5)",
        ["mtf.trigger_timeframes"] = "Trigger bổ sung (VD: M1,M3)",
        ["mtf.logic"] = "Kết hợp xác nhận thêm",
        ["risk.sizing_mode"] = "Cách tính khối lượng", ["risk.risk_percent"] = "Risk mỗi lệnh (%)",
        ["risk.fixed_lot"] = "Lot cố định", ["risk.max_lot"] = "Max lot", ["risk.max_daily_loss_pct"] = "Lỗ tối đa ngày (%)",
        ["risk.max_trades_per_day"] = "Số lệnh / ngày", ["risk.max_open_positions"] = "Số vị thế tối đa",
        ["risk.cooldown_minutes"] = "Chờ giữa lệnh (phút)", ["risk.max_consecutive_losses"] = "Số lệnh thua liên tiếp",
        ["risk.stop_after_daily_target"] = "Dừng khi đạt mục tiêu", ["risk.daily_target_pct"] = "Mục tiêu ngày (%)",
        ["direction.ma_enabled"] = "Lọc theo MA xu hướng", ["direction.ma_type"] = "Loại MA", ["direction.ma_period"] = "Chu kỳ MA",
        ["direction.price_source"] = "Giá tham chiếu", ["direction.require_close_side"] = "Nến đóng cùng hướng",
        ["direction.open_filter_enabled"] = "Bật lọc giá mở cửa", ["direction.open_reference_mode"] = "Giá mở tham chiếu",
        ["pullback.logic"] = "Logic kết hợp", ["pullback.rsi_enabled"] = "Bật bộ lọc RSI", ["pullback.rsi_period"] = "Chu kỳ RSI",
        ["pullback.rsi_buy_level"] = "RSI mua (≤)", ["pullback.rsi_sell_level"] = "RSI bán (≥)",
        ["pullback.z_enabled"] = "Bật Z-Score", ["pullback.z_period"] = "Chu kỳ Z-Score", ["pullback.z_buy_level"] = "Z-Score mua (≤)", ["pullback.z_sell_level"] = "Z-Score bán (≥)",
        ["trigger.logic"] = "Logic xác nhận", ["trigger.rsi_enabled"] = "Xác nhận RSI", ["trigger.rsi_period"] = "Chu kỳ RSI",
        ["trigger.rsi_reversal_delta"] = "RSI đảo chiều (Δ)", ["trigger.z_enabled"] = "Xác nhận Z-Score", ["trigger.z_period"] = "Chu kỳ Z-Score",
        ["trigger.z_reversal_delta"] = "Z đảo chiều (Δ)", ["trigger.confirm_closed_bar"] = "Xác nhận nến đóng",
        ["timeframes.direction"] = "Direction TF", ["timeframes.pullback"] = "Pullback TF", ["timeframes.trigger"] = "Trigger TF",
        ["stop_loss.mode"] = "Kiểu SL", ["stop_loss.fixed_price_units"] = "SL cố định (giá)", ["stop_loss.atr_timeframe"] = "Khung ATR",
        ["stop_loss.atr_period"] = "ATR Period", ["stop_loss.atr_multiplier"] = "Hệ số ATR", ["stop_loss.structure_timeframe"] = "Khung cấu trúc",
        ["stop_loss.structure_lookback"] = "Số nến cấu trúc", ["stop_loss.structure_buffer_price_units"] = "Đệm cấu trúc (giá)",
        ["stop_loss.min_price_units"] = "SL tối thiểu (giá)", ["stop_loss.max_price_units"] = "SL tối đa (giá)",
        ["take_profit.mode"] = "Kiểu TP", ["take_profit.fixed_price_units"] = "TP cố định (giá)", ["take_profit.rr_ratio"] = "Tỷ lệ R:R",
        ["news.enabled"] = "Bật lọc tin tức", ["news.minutes_before"] = "Trước tin (phút)", ["news.minutes_after"] = "Sau tin (phút)", ["news.high_impact_only"] = "Chỉ tin mạnh",
        ["sessions.session1_enabled"] = "Bật phiên 1", ["sessions.session1_start"] = "Bắt đầu", ["sessions.session1_end"] = "Kết thúc",
        ["sessions.session2_enabled"] = "Bật phiên 2", ["sessions.session2_start"] = "Bắt đầu", ["sessions.session2_end"] = "Kết thúc",
        ["management.breakeven_enabled"] = "Breakeven", ["management.breakeven_trigger_rr"] = "Kích hoạt BE (R)",
        ["management.partial_close_enabled"] = "Chốt một phần", ["management.partial_close_percent"] = "Tỷ lệ chốt (%)", ["management.trailing_enabled"] = "Trailing Stop",
        ["take_profit.dynamic.near_tp_distance"] = "Gần TP (giá)", ["take_profit.dynamic.max_extension_price_units"] = "Mở rộng (giá)",
        ["strategy.symbol"] = "Symbol", ["strategy.allow_buy"] = "Cho phép BUY", ["strategy.allow_sell"] = "Cho phép SELL"
    };

    private Control CreateEditor(FieldDescriptor descriptor)
    {
        if (string.Equals(descriptor.Kind, "bool", StringComparison.OrdinalIgnoreCase))
        {
            var check = new CheckBox
            {
                [LocalizationService.TextProperty] = "Bật",
                Foreground = new SolidColorBrush(Color.Parse("#DCE8F4"))
            };
            check.Click += (_, _) => EditorValueChanged(descriptor, check);
            return check;
        }

        if (string.Equals(descriptor.Kind, "enum", StringComparison.OrdinalIgnoreCase))
        {
            var combo = new ComboBox
            {
                ItemsSource = descriptor.EnumValues,
                MinHeight = 27
            };
            if (descriptor.Path is "stop_loss.mode" or "take_profit.mode")
                combo.ItemTemplate = new Avalonia.Controls.Templates.FuncDataTemplate<string>((value, _) => new TextBlock
                {
                    [LocalizationService.TextProperty] = value switch { "STRUCTURE" => "Cấu trúc", "FIXED" => "Cố định", "ZRSI_DYNAMIC" => "Động RSI/Z", "RR" => "R:R", _ => value },
                    [AppearanceService.BaseFontSizeProperty] = 12d,
                    VerticalAlignment = VerticalAlignment.Center
                });
            combo.SelectionChanged += (_, _) => EditorValueChanged(descriptor, combo);
            combo.SelectionChanged += (_, _) => ToolTip.SetTip(combo, $"{descriptor.Path}: {combo.SelectedItem}");
            return combo;
        }

        var text = new TextBox
        {
            MinHeight = 27,
            PlaceholderText = descriptor.Kind switch
            {
                "int" => "Số nguyên",
                "float" => "Số",
                "time" => "HH:MM",
                _ => "Giá trị"
            }
        };
        text.TextChanged += (_, _) => EditorValueChanged(descriptor, text);
        return text;
    }

    private void EditorValueChanged(FieldDescriptor descriptor, Control editor)
    {
        if (_suppressChanges || _draft is null || descriptor.LockedValue is not null)
            return;

        JsonNode? value = editor switch
        {
            CheckBox check => JsonValue.Create(check.IsChecked == true),
            ComboBox combo => JsonValue.Create(combo.SelectedItem?.ToString() ?? string.Empty),
            TextBox text => JsonValue.Create(text.Text ?? string.Empty),
            _ => null
        };

        // Avalonia may deliver TextChanged after a profile-load suppression
        // scope. An unchanged displayed value is not a user edit.
        if (string.Equals(GetDraftValue(descriptor.Path)?.ToString(), value?.ToString(), StringComparison.Ordinal))
            return;
        SetDraftValue(descriptor.Path, value);
        _dirty = true;
        UpdateDirtyStatus();
        UpdateQuickValues();
        this.FindControl<TextBlock>("ValidationStateText")!.Text = "NOT VALIDATED";
        this.FindControl<TextBlock>("ValidationStateText")!.Foreground = Brushes.Gold;
    }

    private void LoadDraft(JsonElement profile, bool dirty)
    {
        var parsed = JsonNode.Parse(profile.GetRawText()) as JsonObject
            ?? throw new InvalidDataException("Profile root must be an object.");

        _draft = parsed;
        _suppressChanges = true;

        try
        {
            foreach (var binding in _fields)
            {
                var value = GetDraftValue(binding.Descriptor.Path);
                SetEditorValue(binding.Editor, binding.Descriptor, value);
            }
        }
        finally
        {
            _suppressChanges = false;
        }

        _dirty = dirty;
        UpdateDirtyStatus();
        UpdateQuickValues();
        this.FindControl<TextBlock>("ValidationStateText")!.Text = "NOT VALIDATED";
        this.FindControl<TextBlock>("ValidationStateText")!.Foreground = Brushes.Gold;
    }

    private static void SetEditorValue(Control editor, FieldDescriptor descriptor, JsonNode? value)
    {
        if (editor is CheckBox check)
        {
            bool parsed = false;
            if (value is JsonValue jsonValue && jsonValue.TryGetValue<bool>(out var boolValue))
                parsed = boolValue;
            check.IsChecked = parsed;
            return;
        }

        if (editor is ComboBox combo)
        {
            string current = value?.ToString() ?? string.Empty;
            combo.SelectedItem = descriptor.EnumValues.FirstOrDefault(
                item => string.Equals(item, current, StringComparison.OrdinalIgnoreCase));
            return;
        }

        if (editor is TextBox text)
            text.Text = value?.ToString() ?? string.Empty;
    }

    private void UpdateQuickValues()
    {
        if (_draft is null)
            return;

        string profileName = GetDraftValue("profile.name")?.ToString() ?? "—";
        this.FindControl<TextBlock>("ProfileNameText")!.Text = profileName;
        this.FindControl<TextBlock>("ProfileHeaderText")!.Text = profileName;
        this.FindControl<TextBlock>("DirectionQuickValue")!.Text =
            GetDraftValue("timeframes.direction")?.ToString() ?? "—";
        this.FindControl<TextBlock>("PullbackQuickValue")!.Text =
            GetDraftValue("timeframes.pullback")?.ToString() ?? "—";
        this.FindControl<TextBlock>("TriggerQuickValue")!.Text =
            GetDraftValue("timeframes.trigger")?.ToString() ?? "—";
    }

    private void UpdateDirtyStatus()
    {
        var text = this.FindControl<TextBlock>("DirtyStateText")!;
        text.Text = _dirty ? "UNSAVED CHANGES" : "UNCHANGED";
        text.Foreground = _dirty ? Brushes.Gold : Brushes.LightGreen;
    }

    private async void Defaults_OnClick(object? sender, RoutedEventArgs e)
    {
        await RunUiActionAsync(async () =>
        {
            EnsureSupervisorReady();
            var profile = await _supervisor!.GetDefaultConfigAsync();
            LoadDraft(profile, dirty: true);
            SetStatus("Đã nạp mặc định canonical. Bấm Áp dụng Active để dùng trong Engine.", Brushes.LightGreen);
        });
    }

    private async void ReloadActive_OnClick(object? sender, RoutedEventArgs e)
    {
        await RunUiActionAsync(async () =>
        {
            EnsureSupervisorReady();
            var profile = await _supervisor!.GetActiveConfigAsync();
            LoadDraft(profile, dirty: false);
            SetStatus("Đã hoàn tác draft về active profile hiện tại của Engine.", Brushes.LightGreen);
        });
    }

    private async void Validate_OnClick(object? sender, RoutedEventArgs e)
    {
        await RunUiActionAsync(async () =>
        {
            var result = await ValidateDraftAsync();
            if (result.Valid)
                SetStatus("Cấu hình hợp lệ. Không có safety/range lỗi.", Brushes.LightGreen);
            else
                ShowValidationErrors(result.Errors);
        });
    }

    private async void Apply_OnClick(object? sender, RoutedEventArgs e)
    {
        await RunUiActionAsync(async () =>
        {
            EnsureSupervisorReady();
            if (HasConflictingDraft?.Invoke() == true)
                throw new InvalidOperationException("Một tab khác có bản nháp chưa áp dụng. Hãy áp dụng hoặc hoàn tác bản nháp đó trước.");
            var validation = await ValidateDraftAsync();
            if (!validation.Valid || validation.Profile is null)
            {
                ShowValidationErrors(validation.Errors);
                return;
            }

            var apply = await _supervisor!.ApplyActiveConfigAsync(validation.Profile.Value);
            if (!apply.Applied || apply.Profile is null)
            {
                ShowValidationErrors(apply.Errors);
                return;
            }

            LoadDraft(apply.Profile.Value, dirty: false);
            this.FindControl<TextBlock>("ValidationStateText")!.Text = "VALID + ACTIVE";
            this.FindControl<TextBlock>("ValidationStateText")!.Foreground = Brushes.LightGreen;
            SetStatus("Đã xác thực và áp dụng profile. Quyền giao dịch giữ theo lựa chọn tại tab Lệnh & Vị thế.", Brushes.LightGreen);
        });
    }

    private async void LoadJson_OnClick(object? sender, RoutedEventArgs e)
    {
        await RunUiActionAsync(async () =>
        {
            var storage = RequireStorageProvider();
            var files = await storage.OpenFilePickerAsync(new FilePickerOpenOptions
            {
                Title = "Mở XAUPY profile JSON",
                AllowMultiple = false,
                FileTypeFilter = new[] { JsonFileType }
            });

            var file = files.FirstOrDefault();
            if (file is null)
                return;

            await using var stream = await file.OpenReadAsync();
            using var document = await JsonDocument.ParseAsync(stream);
            if (document.RootElement.ValueKind != JsonValueKind.Object)
                throw new InvalidDataException("JSON root phải là object.");

            EnsureSupervisorReady();
            var validation = await _supervisor!.ValidateConfigAsync(document.RootElement.Clone());
            if (!validation.Valid || validation.Profile is null)
            {
                ShowValidationErrors(validation.Errors);
                return;
            }

            LoadDraft(validation.Profile.Value, dirty: true);
            _currentJsonFile = file;
            _lastSetTemplatePath = null;
            SetStatus($"Đã mở JSON: {file.Name}. Draft chưa được Apply.", Brushes.LightGreen);
        });
    }

    private async void SaveJson_OnClick(object? sender, RoutedEventArgs e)
    {
        await RunUiActionAsync(async () =>
        {
            var validation = await ValidateDraftAsync();
            if (!validation.Valid || validation.Profile is null)
            {
                ShowValidationErrors(validation.Errors);
                return;
            }

            var storage = RequireStorageProvider();
            var file = (sender as Button)?.Tag as string != "save-as" ? _currentJsonFile : null;
            file ??= await storage.SaveFilePickerAsync(new FilePickerSaveOptions
            {
                Title = "Lưu XAUPY profile JSON",
                SuggestedFileName = SuggestedProfileFileName(),
                DefaultExtension = "json",
                FileTypeChoices = new[] { JsonFileType }
            });

            if (file is null)
                return;

            await FileOutput.WriteTextAsync(file, JsonSerializer.Serialize(validation.Profile.Value, new JsonSerializerOptions { WriteIndented = true }));
            _currentJsonFile = file;

            SetStatus($"Đã lưu profile JSON: {file.Name}.", Brushes.LightGreen);
        });
    }

    private async void ImportSet_OnClick(object? sender, RoutedEventArgs e)
    {
        await RunUiActionAsync(async () =>
        {
            EnsureConfigToolExists();

            var storage = RequireStorageProvider();
            var files = await storage.OpenFilePickerAsync(new FilePickerOpenOptions
            {
                Title = "Nhập preset MT5 .set",
                AllowMultiple = false,
                FileTypeFilter = new[] { SetFileType }
            });

            var file = files.FirstOrDefault();
            if (file is null)
                return;

            string inputPath = file.Path.LocalPath;
            var validation = await ValidateDraftAsync();
            if (!validation.Valid || validation.Profile is null)
            {
                ShowValidationErrors(validation.Errors);
                return;
            }

            string tempRoot = CreateTempDirectory();
            try
            {
                string baseProfile = Path.Combine(tempRoot, "base.json");
                string outputProfile = Path.Combine(tempRoot, "imported.json");
                string reportPath = Path.Combine(tempRoot, "report.json");

                await File.WriteAllTextAsync(
                    baseProfile,
                    JsonSerializer.Serialize(
                        validation.Profile.Value,
                        new JsonSerializerOptions { WriteIndented = true }),
                    Encoding.UTF8);

                var result = await RunConfigToolAsync(new[]
                {
                    "import-set",
                    inputPath,
                    "--base-profile", baseProfile,
                    "--out", outputProfile,
                    "--report", reportPath
                });

                if (result.ExitCode != 0)
                    throw new InvalidOperationException($"xaupy-config import-set failed: {result.StandardError}");

                using var importedDocument = JsonDocument.Parse(await File.ReadAllTextAsync(outputProfile));
                EnsureSupervisorReady();
                var importedValidation = await _supervisor!.ValidateConfigAsync(importedDocument.RootElement.Clone());

                if (!importedValidation.Valid || importedValidation.Profile is null)
                {
                    ShowValidationErrors(importedValidation.Errors);
                    return;
                }

                int unknownCount = 0;
                if (File.Exists(reportPath))
                {
                    using var report = JsonDocument.Parse(await File.ReadAllTextAsync(reportPath));
                    if (report.RootElement.TryGetProperty("unknown_count", out var unknown) &&
                        unknown.TryGetInt32(out var count))
                    {
                        unknownCount = count;
                    }
                }

                LoadDraft(importedValidation.Profile.Value, dirty: true);
                _lastSetTemplatePath = inputPath;
                SetStatus(
                    $"Đã nhập {file.Name}. Unknown/preserved keys: {unknownCount}. Xuất .set sẽ dùng file này làm template.",
                    Brushes.LightGreen);
            }
            finally
            {
                TryDeleteDirectory(tempRoot);
            }
        });
    }

    private async void ExportSet_OnClick(object? sender, RoutedEventArgs e)
    {
        await RunUiActionAsync(async () =>
        {
            EnsureConfigToolExists();

            var validation = await ValidateDraftAsync();
            if (!validation.Valid || validation.Profile is null)
            {
                ShowValidationErrors(validation.Errors);
                return;
            }

            var storage = RequireStorageProvider();
            var file = await storage.SaveFilePickerAsync(new FilePickerSaveOptions
            {
                Title = "Xuất MT5 .set",
                SuggestedFileName = Path.ChangeExtension(SuggestedProfileFileName(), ".set"),
                DefaultExtension = "set",
                FileTypeChoices = new[] { SetFileType }
            });

            if (file is null)
                return;

            string? savedPath = file.TryGetLocalPath();
            string tempRoot = CreateTempDirectory();
            string outputPath = Path.Combine(tempRoot,"exported.set");

            try
            {
                string profilePath = Path.Combine(tempRoot, "profile.json");
                await File.WriteAllTextAsync(
                    profilePath,
                    JsonSerializer.Serialize(
                        validation.Profile.Value,
                        new JsonSerializerOptions { WriteIndented = true }),
                    Encoding.UTF8);

                var arguments = new List<string>
                {
                    "export-set",
                    profilePath
                };

                if (!string.IsNullOrWhiteSpace(_lastSetTemplatePath) &&
                    File.Exists(_lastSetTemplatePath))
                {
                    arguments.Add("--template");
                    arguments.Add(_lastSetTemplatePath);
                }

                arguments.Add("--out");
                arguments.Add(outputPath);

                var result = await RunConfigToolAsync(arguments);
                if (result.ExitCode != 0)
                    throw new InvalidOperationException($"xaupy-config export-set failed: {result.StandardError}");

                await using (var exported = File.OpenRead(outputPath)) await FileOutput.CopyAsync(file,exported);
                _lastSetTemplatePath = savedPath;
                SetStatus(
                    $"Đã xuất {file.Name}" +
                    (arguments.Contains("--template") ? " theo template đã nhập." : " dạng canonical UTF-16LE."),
                    Brushes.LightGreen);
            }
            finally
            {
                TryDeleteDirectory(tempRoot);
            }
        });
    }

    private async Task<ConfigValidationResult> ValidateDraftAsync()
    {
        EnsureSupervisorReady();

        if (_draft is null)
            throw new InvalidOperationException("Draft profile chưa được tải.");

        JsonElement element = JsonSerializer.SerializeToElement(_draft);
        var result = await _supervisor!.ValidateConfigAsync(element);

        var state = this.FindControl<TextBlock>("ValidationStateText")!;
        state.Text = result.Valid ? "VALID" : $"INVALID ({result.Errors.Count})";
        state.Foreground = result.Valid ? Brushes.LightGreen : Brushes.IndianRed;

        return result;
    }

    private void ShowValidationErrors(IReadOnlyList<string> errors)
    {
        string detail = errors.Count == 0
            ? "Cấu hình không hợp lệ."
            : string.Join(" • ", errors.Take(6)) +
              (errors.Count > 6 ? $" • ... +{errors.Count - 6} lỗi" : string.Empty);

        SetStatus(detail, Brushes.IndianRed);
    }

    private async Task RunUiActionAsync(Func<Task> action)
    {
        if (_loading)
            return;

        _loading = true;
        try
        {
            await action();
        }
        catch (Exception ex)
        {
            SetStatus(ex.Message, Brushes.IndianRed);
        }
        finally
        {
            _loading = false;
        }
    }

    private void SearchBox_OnTextChanged(object? sender, TextChangedEventArgs e)
    {
        ApplySearchFilter();
    }

    private void ApplySearchFilter()
    {
        string query = this.FindControl<TextBox>("SearchBox")?.Text?.Trim().ToLowerInvariant()
                       ?? string.Empty;
        int visible = 0;

        foreach (var field in _fields)
        {
            string haystack =
                $"{field.Descriptor.Path} {field.Descriptor.SetKey} {field.Descriptor.Description} {field.GroupKey}"
                    .ToLowerInvariant();

            bool show = string.IsNullOrEmpty(query) || haystack.Contains(query, StringComparison.Ordinal);
            field.Row.IsVisible = show;
            if (show)
                visible++;
        }

        foreach (var group in _groups.Values)
            group.Card.IsVisible = group.Fields.Any(field => field.Row.IsVisible);

        var countText = this.FindControl<TextBlock>("VisibleCountText");
        if (countText is not null)
            countText.Text = $"{visible} / {_fields.Count}";
    }

    private void SetDraftValue(string path, JsonNode? value)
    {
        if (_draft is null)
            return;

        string[] parts = path.Split('.');
        JsonObject current = _draft;

        for (int i = 0; i < parts.Length - 1; i++)
        {
            if (current[parts[i]] is not JsonObject child)
            {
                child = new JsonObject();
                current[parts[i]] = child;
            }

            current = child;
        }

        current[parts[^1]] = value;
    }

    private JsonNode? GetDraftValue(string path)
    {
        JsonNode? current = _draft;

        foreach (var part in path.Split('.'))
        {
            if (current is not JsonObject obj)
                return null;
            current = obj[part];
        }

        return current;
    }

    private static string GroupKey(string path)
    {
        if (path.StartsWith("filters.adx.", StringComparison.Ordinal))
            return "filters.adx";
        if (path.StartsWith("filters.atr.", StringComparison.Ordinal))
            return "filters.atr";
        if (path.StartsWith("filters.open.", StringComparison.Ordinal))
            return "filters.open";
        if (path.StartsWith("take_profit.dynamic.", StringComparison.Ordinal))
            return "take_profit.dynamic";

        int dot = path.IndexOf('.');
        return dot > 0 ? path[..dot] : path;
    }

    private static (int Order, string Title) GroupTitle(string key)
    {
        return GroupTitles.TryGetValue(key, out var value)
            ? value
            : (999, key);
    }

    private static string BoundsText(FieldDescriptor descriptor)
    {
        if (descriptor.EnumValues.Count > 0)
            return $"{descriptor.EnumValues.Count} lựa chọn";

        if (descriptor.Minimum is not null && descriptor.Maximum is not null)
            return $"Min {descriptor.Minimum:g} • Max {descriptor.Maximum:g}";

        if (descriptor.Minimum is not null)
            return $"Min {descriptor.Minimum:g}";

        if (descriptor.Maximum is not null)
            return $"Max {descriptor.Maximum:g}";

        return string.Empty;
    }

    private void EnsureSupervisorReady()
    {
        if (_supervisor is null)
            throw new InvalidOperationException("Configuration editor chưa gắn Engine supervisor.");

        if (_supervisor.State != EngineConnectionState.Ready)
            throw new InvalidOperationException("Python Engine chưa READY.");
    }

    private IStorageProvider RequireStorageProvider()
    {
        var top = TopLevel.GetTopLevel(this)
                  ?? throw new InvalidOperationException("Không tìm thấy TopLevel.");

        if (!top.StorageProvider.CanOpen || !top.StorageProvider.CanSave)
            throw new InvalidOperationException("Storage provider không hỗ trợ open/save file.");

        return top.StorageProvider;
    }

    private string ConfigToolPath =>
        Path.Combine(
            AppContext.BaseDirectory,
            "tools",
            OperatingSystem.IsWindows() ? "xaupy-config.exe" : "xaupy-config");

    private void EnsureConfigToolExists()
    {
        if (!File.Exists(ConfigToolPath))
            throw new FileNotFoundException(
                "Không tìm thấy tools/xaupy-config.exe. Hãy dùng full Task 006 build.",
                ConfigToolPath);
    }

    private async Task<(int ExitCode, string StandardOutput, string StandardError)> RunConfigToolAsync(
        IEnumerable<string> arguments)
    {
        var startInfo = new ProcessStartInfo
        {
            FileName = ConfigToolPath,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true
        };

        foreach (var argument in arguments)
            startInfo.ArgumentList.Add(argument);

        using var process = Process.Start(startInfo)
            ?? throw new InvalidOperationException("Không thể khởi động xaupy-config.");

        string stdout = await process.StandardOutput.ReadToEndAsync();
        string stderr = await process.StandardError.ReadToEndAsync();
        await process.WaitForExitAsync();

        return (process.ExitCode, stdout, stderr);
    }

    private static string CreateTempDirectory()
    {
        string path = Path.Combine(Path.GetTempPath(), "XAUPY", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(path);
        return path;
    }

    private static void TryDeleteDirectory(string path)
    {
        try
        {
            if (Directory.Exists(path))
                Directory.Delete(path, recursive: true);
        }
        catch
        {
        }
    }

    private string SuggestedProfileFileName()
    {
        string name = GetDraftValue("profile.name")?.ToString() ?? "XAUPY_Profile";
        foreach (char invalid in Path.GetInvalidFileNameChars())
            name = name.Replace(invalid, '_');

        if (string.IsNullOrWhiteSpace(name))
            name = "XAUPY_Profile";

        return name + ".json";
    }

    private void SetStatus(string text, IBrush color)
    {
        var status = this.FindControl<TextBlock>("StatusText");
        if (status is null)
            return;

        status.Text = text;
        status.Foreground = color;
    }

    private static string ReadRequiredString(JsonElement parent, string name)
    {
        return ReadOptionalString(parent, name)
               ?? throw new InvalidDataException($"Schema field missing {name}.");
    }

    private static string? ReadOptionalString(JsonElement parent, string name)
    {
        return parent.TryGetProperty(name, out var value) &&
               value.ValueKind == JsonValueKind.String
            ? value.GetString()
            : null;
    }

    private static double? TryReadNullableDouble(JsonElement parent, string name)
    {
        if (!parent.TryGetProperty(name, out var value) ||
            value.ValueKind == JsonValueKind.Null ||
            value.ValueKind == JsonValueKind.Undefined)
        {
            return null;
        }

        return value.ValueKind == JsonValueKind.Number && value.TryGetDouble(out var number)
            ? number
            : null;
    }
}
