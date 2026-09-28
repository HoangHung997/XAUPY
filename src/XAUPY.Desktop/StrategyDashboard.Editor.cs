using System.Globalization;
using System.Text.Json;
using System.Text.Json.Nodes;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Layout;
using Avalonia.Media;
using XAUPY.Ipc;

namespace XAUPY.Desktop;

public partial class StrategyDashboard
{
    private readonly Dictionary<string, Control> _strategyFields = new();
    private JsonObject? _strategyBaseline;
    private bool _strategySync;
    private Task? _strategyLoad;
    private string _strategyLoadedHash = "";
    public bool HasUnsavedChanges { get; private set; }
    public Func<bool>? HasConflictingDraft { get; set; }

    private void InitializeStrategyEditor()
    {
        string[] frames = ["M1", "M3", "M5", "M15", "M30", "H1", "H2", "H4", "D1"];
        foreach (var role in new[] { "Direction", "Pullback", "Trigger" })
        {
            var selector = Choice("timeframes." + role.ToLowerInvariant(), frames);
            selector.Height = 36;
            ((ComboBox)selector).SetValue(AppearanceService.BaseFontSizeProperty, 16d);
            Host(role + "Editor").Children.Add(selector);
        }
        Host("ZEditor").Children.Add(Toggles(("pullback.z_enabled", "Pullback"), ("trigger.z_enabled", "Trigger")));
        Host("ZEditor").Children.Add(Pair("Chu kỳ Z", Number("pullback.z_period", 2, 500, true),
                                              "Hồi Z (Trigger)", Number("trigger.z_reversal_delta", 0, 10)));
        Host("ZEditor").Children.Add(Pair("Ngưỡng BUY", Number("pullback.z_buy_level", -10, 10),
                                              "Ngưỡng SELL", Number("pullback.z_sell_level", -10, 10)));
        Host("RsiEditor").Children.Add(Toggles(("pullback.rsi_enabled", "Pullback"), ("trigger.rsi_enabled", "Trigger")));
        Host("RsiEditor").Children.Add(Pair("Chu kỳ RSI", Number("pullback.rsi_period", 2, 200, true),
                                                "Hồi RSI (Trigger)", Number("trigger.rsi_reversal_delta", 0, 50)));
        Host("RsiEditor").Children.Add(Pair("Ngưỡng BUY", Number("pullback.rsi_buy_level", 0, 100),
                                                "Ngưỡng SELL", Number("pullback.rsi_sell_level", 0, 100)));
        Host("AdxEditor").Children.Add(Toggle("filters.adx.enabled", "Bật bộ lọc ADX"));
        Host("AdxEditor").Children.Add(Pair("Chu kỳ", Number("filters.adx.period", 2, 200, true),
                                                "Ngưỡng tối thiểu", Number("filters.adx.min", 0, 100)));
        Host("AdxEditor").Children.Add(Pair("Khung thời gian", Choice("filters.adx.timeframe", frames),
                                                "Ngưỡng tối đa", Number("filters.adx.max", 0, 100)));
        Host("AtrEditor").Children.Add(Toggle("filters.atr.enabled", "Bật bộ lọc ATR"));
        Host("AtrEditor").Children.Add(Pair("Chu kỳ", Number("filters.atr.period", 2, 200, true),
                                                "Ngưỡng tối thiểu", Number("filters.atr.min_price_units", 0, 1000)));
        Host("AtrEditor").Children.Add(Pair("Khung thời gian", Choice("filters.atr.timeframe", frames),
                                                "Ngưỡng tối đa", Number("filters.atr.max_price_units", 0, 10000)));
        Host("SessionEditor").Children.Add(Toggles(("sessions.session1_enabled", "Phiên 1"), ("sessions.session2_enabled", "Phiên 2")));
        Host("SessionEditor").Children.Add(Pair("Phiên 1 bắt đầu", Input("sessions.session1_start"),
                                                    "Kết thúc", Input("sessions.session1_end")));
        Host("SessionEditor").Children.Add(Pair("Phiên 2 bắt đầu", Input("sessions.session2_start"),
                                                    "Kết thúc", Input("sessions.session2_end")));
        Host("StopsEditor").Children.Add(Pair("Stop Loss", Choice("stop_loss.mode", ["FIXED", "ATR", "STRUCTURE"]),
                                                  "Take Profit", Choice("take_profit.mode", ["FIXED", "RR", "ZRSI_DYNAMIC"])));
        Host("StopsEditor").Children.Add(Pair("SL cố định (giá)", Number("stop_loss.fixed_price_units", .01m, 1000),
                                                  "TP cố định (giá)", Number("take_profit.fixed_price_units", .01m, 10000)));
        Host("LogicEditor").Children.Add(Pair("Pullback", Choice("pullback.logic", ["AND", "OR"]),
                                                  "Trigger", Choice("trigger.logic", ["AND", "OR"])));
        Host("AdvancedEditor").Children.Add(Toggle("trigger.confirm_closed_bar", "Chỉ xác nhận khi nến đóng"));
        Host("SupplementalEditor").Children.Add(Pair("Chu kỳ RSI Trigger", Number("trigger.rsi_period", 2, 200, true),
                                                     "Chu kỳ Z Trigger", Number("trigger.z_period", 2, 500, true)));
        Host("SupplementalEditor").Children.Add(Toggles(("strategy.allow_buy", "Cho phép BUY"), ("strategy.allow_sell", "Cho phép SELL")));
        var ageRow = new Grid { ColumnDefinitions = new ColumnDefinitions("*,110"), ColumnSpacing = 8 };
        ageRow.Children.Add(new TextBlock { [LocalizationService.TextProperty] = "Hạn tín hiệu (nến)", [AppearanceService.BaseFontSizeProperty] = 12d, VerticalAlignment = VerticalAlignment.Center });
        var age = Number("entry.max_signal_age_bars", 1, 100, true); Grid.SetColumn(age, 1); ageRow.Children.Add(age);
        Host("AdvancedEditor").Children.Add(ageRow);
    }

    private StackPanel Host(string name) => this.FindControl<StackPanel>(name)!;
    private Control Register(string path, Control control)
    {
        control.Tag = path;
        control.HorizontalAlignment = HorizontalAlignment.Stretch;
        control.MinHeight = 20;
        control.Height = control is CheckBox ? 20 : 22;
        control.IsEnabled = false;
        _strategyFields.Add(path, control);
        return control;
    }
    private Control Choice(string path, string[] options)
    {
        var control = new ComboBox { ItemsSource = options, [AppearanceService.BaseFontSizeProperty] = 13d, Padding = new Thickness(7, 2) };
        control.SelectionChanged += (_, _) => StrategyEdited();
        return Register(path, control);
    }
    private Control Number(string path, decimal min, decimal max, bool integer = false)
    {
        var control = new NumericUpDown { Minimum = min, Maximum = max, Increment = integer ? 1 : .1m,
            FormatString = integer ? "0" : "0.##", [AppearanceService.BaseFontSizeProperty] = 13d, Padding = new Thickness(5, 1),
            Background = new SolidColorBrush(Color.Parse("#0C2942")), BorderBrush = new SolidColorBrush(Color.Parse("#285573")),
            AllowSpin = true, ShowButtonSpinner = false };
        control.ValueChanged += (_, _) => StrategyEdited();
        return Register(path, control);
    }
    private Control Input(string path)
    {
        var control = new TextBox { [AppearanceService.BaseFontSizeProperty] = 13d, Padding = new Thickness(7, 3) };
        control.TextChanged += (_, _) => StrategyEdited();
        return Register(path, control);
    }
    private Control Toggle(string path, string label)
    {
        var control = new CheckBox { [LocalizationService.TextProperty] = label, [AppearanceService.BaseFontSizeProperty] = 13d, Padding = new Thickness(5, 0) };
        control.IsCheckedChanged += (_, _) => StrategyEdited();
        return Register(path, control);
    }
    private Control Toggles(params (string Path, string Label)[] fields)
    {
        var row = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 9 };
        foreach (var (path, label) in fields) row.Children.Add(Toggle(path, label));
        return row;
    }
    private static Control Pair(string leftLabel, Control left, string rightLabel, Control right)
    {
        var row = new Grid { ColumnDefinitions = new ColumnDefinitions("*,*"), ColumnSpacing = 8 };
        var a = new StackPanel { Spacing = 0, Children = { new TextBlock { [LocalizationService.TextProperty] = leftLabel, [AppearanceService.BaseFontSizeProperty] = 12d, Foreground = Brushes.LightSteelBlue }, left } };
        var b = new StackPanel { Spacing = 0, Children = { new TextBlock { [LocalizationService.TextProperty] = rightLabel, [AppearanceService.BaseFontSizeProperty] = 12d, Foreground = Brushes.LightSteelBlue }, right } };
        Grid.SetColumn(b, 1); row.Children.Add(a); row.Children.Add(b);
        return row;
    }
    private static JsonNode? ValueAt(JsonObject profile, string path)
    {
        JsonNode? value = profile;
        foreach (string part in path.Split('.')) value = value?[part];
        return value;
    }
    private static void Put(JsonObject profile, string path, JsonNode? value)
    {
        string[] parts = path.Split('.'); JsonNode node = profile;
        foreach (var part in parts[..^1]) node = node[part]!;
        node[parts[^1]] = value?.DeepClone();
    }
    private static JsonNode? ReadControl(Control control) => control switch
    {
        CheckBox check => JsonValue.Create(check.IsChecked == true),
        ComboBox combo => JsonValue.Create(combo.SelectedItem?.ToString()),
        NumericUpDown number when number.FormatString == "0" => number.Value.HasValue ? JsonValue.Create((int)number.Value.Value) : null,
        NumericUpDown number => number.Value.HasValue ? JsonValue.Create((double)number.Value.Value) : null,
        TextBox input => JsonValue.Create(input.Text ?? ""),
        _ => null
    };
    private void StrategyEdited()
    {
        if (_strategySync || _strategyBaseline is null) return;
        HasUnsavedChanges = _strategyFields.Any(field => !JsonNode.DeepEquals(ReadControl(field.Value), ValueAt(_strategyBaseline, field.Key)));
        this.FindControl<Button>("ApplyStrategyButton")!.SetValue(LocalizationService.TextProperty, HasUnsavedChanges ? "Áp dụng thay đổi" : "Áp dụng cấu hình");
    }
    private void SetStrategyControls(JsonObject profile, bool newBaseline)
    {
        _strategySync = true;
        try
        {
            if (newBaseline) _strategyBaseline = profile.DeepClone().AsObject();
            foreach (var (path, control) in _strategyFields)
            {
                var value = ValueAt(profile, path);
                switch (control)
                {
                    case CheckBox check: check.IsChecked = value?.GetValue<bool>() == true; break;
                    case ComboBox combo: combo.SelectedItem = value?.GetValue<string>(); break;
                    case NumericUpDown number: number.Value = value is null ? null : decimal.Parse(value.ToJsonString(), CultureInfo.InvariantCulture); break;
                    case TextBox input: input.Text = value?.GetValue<string>() ?? ""; break;
                }
                control.IsEnabled = true;
            }
        }
        finally { _strategySync = false; }
        StrategyEdited();
        Text("StrategyDescriptionText").Text = (ValueAt(profile, "direction.ma_enabled")?.GetValue<bool>() == false
            ? "Không lọc hướng bằng MA; "
            : $"Theo hướng {ValueAt(profile, "direction.ma_type")}{ValueAt(profile, "direction.ma_period")}; ") +
            $"tìm nhịp hồi ở {ValueAt(profile, "timeframes.pullback")}, xác nhận ở {ValueAt(profile, "timeframes.trigger")}. " +
            (ValueAt(profile, "trigger.confirm_closed_bar")?.GetValue<bool>() == true ? "Đánh giá nến đóng." : "Ghi nhớ cực trị RSI/Z theo tick; xác nhận từ nến sau.");
        var rules = Host("StrategyRulesHost");
        rules.Children.Clear();
        string Read(string path) => ValueAt(profile, path)?.ToString() ?? "—";
        foreach (var (label, value) in new[] {
            ("RSI Pullback", $"{Read("pullback.rsi_buy_level")} / {Read("pullback.rsi_sell_level")} ({Read("pullback.rsi_period")})"),
            ("Z-Score Pullback", $"{Read("pullback.z_buy_level")} / {Read("pullback.z_sell_level")} ({Read("pullback.z_period")})"),
            ("Đảo chiều RSI / Z", $"{Read("trigger.rsi_reversal_delta")} / {Read("trigger.z_reversal_delta")}"),
            ("ADX / ATR", $"{(Read("filters.adx.enabled") == "true" ? Read("filters.adx.min") : "Tắt")} / {(Read("filters.atr.enabled") == "true" ? Read("filters.atr.min_price_units") : "Tắt")}"),
            ("SL / TP Mode", $"{Read("stop_loss.mode")} / {Read("take_profit.mode")}"),
            ("Logic Pullback / Trigger", $"{Read("pullback.logic")} / {Read("trigger.logic")}") })
        {
            var row = new Grid { ColumnDefinitions = new ColumnDefinitions("1.4*,1*") };
            row.Children.Add(new Border { Padding = new Thickness(8,4), BorderBrush = new SolidColorBrush(Color.Parse("#123751")), BorderThickness = new Thickness(0,0,1,0), Child = new TextBlock { [LocalizationService.TextProperty] = label, [AppearanceService.BaseFontSizeProperty] = 13d, Foreground = Brushes.LightSteelBlue } });
            var valueCell = new Border { Padding = new Thickness(8,4), Child = new TextBlock { Text = value, [AppearanceService.BaseFontSizeProperty] = 13d, TextWrapping = TextWrapping.Wrap } };
            Grid.SetColumn(valueCell, 1); row.Children.Add(valueCell);
            rules.Children.Add(new Border { BorderBrush = new SolidColorBrush(Color.Parse("#123751")), BorderThickness = new Thickness(0,0,0,1), Child = row });
        }
    }
    private void RefreshStrategyEditor(string profileHash)
    {
        if (_supervisor?.State != EngineConnectionState.Ready || HasUnsavedChanges || _actionBusy ||
            (_strategyLoad is { IsCompleted: false }) || (_strategyBaseline is not null && _strategyLoadedHash == profileHash)) return;
        _strategyLoad = LoadStrategyEditorAsync(profileHash);
    }
    private async Task LoadStrategyEditorAsync(string profileHash)
    {
        try
        {
            var profile = await _supervisor!.GetActiveConfigAsync();
            if (HasUnsavedChanges) return;
            SetStrategyControls(JsonNode.Parse(profile.GetRawText())!.AsObject(), true);
            _strategyLoadedHash = profileHash;
        }
        catch (Exception ex) { ShowAction(ex.Message, Brushes.Gold); }
    }
    private async void ApplyStrategy_OnClick(object? sender, RoutedEventArgs e)
    {
        await RunActionAsync(async supervisor =>
        {
            if (_strategyBaseline is null) throw new InvalidOperationException("Đang tải cấu hình chiến lược.");
            if (HasConflictingDraft?.Invoke() == true)
                throw new InvalidOperationException("Cấu hình hoặc Tổng quan có bản nháp chưa áp dụng. Hãy xử lý bản nháp đó trước.");
            var active = JsonNode.Parse((await supervisor.GetActiveConfigAsync()).GetRawText())!.AsObject();
            foreach (var (path, control) in _strategyFields)
            {
                var proposed = ReadControl(control);
                if (JsonNode.DeepEquals(proposed, ValueAt(_strategyBaseline, path))) continue;
                if (!JsonNode.DeepEquals(ValueAt(active, path), ValueAt(_strategyBaseline, path)))
                    throw new InvalidOperationException("Cấu hình đang chạy đã thay đổi. Bản nháp được giữ; bấm Tải lại để xem cấu hình mới trước khi áp dụng.");
                Put(active, path, proposed);
            }
            var applied = await supervisor.ApplyActiveConfigAsync(JsonSerializer.SerializeToElement(active));
            if (!applied.Applied) throw new InvalidDataException(string.Join(" • ", applied.Errors));
            SetStrategyControls(active, true);
            ShowAction("Đã áp dụng các tham số chiến lược. Quyền giao dịch giữ theo lựa chọn người dùng.", Brushes.LightGreen);
        });
    }
    private async void ResetStrategyDraft_OnClick(object? sender, RoutedEventArgs e)
    {
        await RunActionAsync(async supervisor =>
        {
            SetStrategyControls(JsonNode.Parse((await supervisor.GetActiveConfigAsync()).GetRawText())!.AsObject(), true);
            ShowAction("Đã tải lại cấu hình đang chạy.", Brushes.LightGray);
        });
    }
    private JsonElement BuildStrategyDraft()
    {
        if(_strategyBaseline is null)throw new InvalidOperationException("Đang tải cấu hình chiến lược.");
        var draft=_strategyBaseline.DeepClone().AsObject();
        foreach(var (path,control) in _strategyFields)Put(draft,path,ReadControl(control));
        return JsonSerializer.SerializeToElement(draft);
    }
    private async void SetStartupStrategy_OnClick(object? sender,RoutedEventArgs e)
    {
        await RunActionAsync(async supervisor=>
        {
            var result=await supervisor.SaveStartupProfileAsync(BuildStrategyDraft());
            if(!result.GetProperty("ok").GetBoolean())throw new InvalidDataException(result.GetProperty("errors").ToString());
            ShowAction("Đã lưu bản nháp làm hồ sơ khởi động mặc định. Có hiệu lực ở lần khởi động Engine tiếp theo.",Brushes.LightGreen);
        });
    }
}
