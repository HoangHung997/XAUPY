using System.Text;
using System.Text.Json;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Platform.Storage;
using XAUPY.Ipc;

namespace XAUPY.Desktop;

public partial class StrategyDashboard : UserControl
{
    public void ApplyExecution(ExecutionSnapshot state)
    {
        this.FindControl<TextBlock>("StrategyExecutionText")!.Text = state.Label;
        ToolTip.SetTip(this.FindControl<TextBlock>("StrategyExecutionText")!, state.Reason);
        Text("StopsExecutionText").Text = state.Label;
        Text("ConditionExecutionText").Text = state.Label;
        ToolTip.SetTip(Text("ConditionExecutionText"), state.Reason);
    }
    private EngineProcessSupervisor? _supervisor;
    private bool _actionBusy;
    private static readonly FilePickerFileType StrategyJson = new("XAUPY strategy JSON") { Patterns = ["*.json"] };

    public void AttachSupervisor(EngineProcessSupervisor supervisor) => _supervisor = supervisor;

    public StrategyDashboard()
    {
        InitializeComponent();
        InitializeStrategyEditor();
        Apply(StrategySnapshot.Empty, ConfigurationSummary.Default);
    }

    private async void SaveStrategy_OnClick(object? sender, RoutedEventArgs e)
    {
        await RunActionAsync(async supervisor =>
        {
            var profile = (sender as Button)?.Name == "ExportStrategyButton" ? await supervisor.GetActiveConfigAsync() : BuildStrategyDraft();
            var validation=await supervisor.ValidateConfigAsync(profile);
            if(!validation.Valid)throw new InvalidDataException(string.Join(" • ",validation.Errors));
            var provider = TopLevel.GetTopLevel(this)?.StorageProvider
                ?? throw new InvalidOperationException("Không mở được hộp thoại lưu file.");
            var file = await provider.SaveFilePickerAsync(new FilePickerSaveOptions
            {
                Title = "Lưu chiến lược XAUPY",
                SuggestedFileName = "XAUPY_Strategy.json",
                DefaultExtension = "json",
                FileTypeChoices = [StrategyJson]
            });
            if (file is null) return;
            await using var stream = await file.OpenWriteAsync();
            stream.SetLength(0);
            await using var writer = new StreamWriter(stream, new UTF8Encoding(false));
            await writer.WriteAsync(JsonSerializer.Serialize(profile, new JsonSerializerOptions { WriteIndented = true }));
            ShowAction($"Đã lưu {file.Name}. Bản đang chạy chỉ đổi khi Áp dụng.", Brushes.LightGreen);
        });
    }

    private async void LoadStrategy_OnClick(object? sender, RoutedEventArgs e)
    {
        await RunActionAsync(async supervisor =>
        {
            if (HasConflictingDraft?.Invoke() == true)
                throw new InvalidOperationException("Cấu hình hoặc Tổng quan có bản nháp chưa áp dụng. Hãy xử lý bản nháp đó trước.");
            var provider = TopLevel.GetTopLevel(this)?.StorageProvider
                ?? throw new InvalidOperationException("Không mở được hộp thoại chọn file.");
            var files = await provider.OpenFilePickerAsync(new FilePickerOpenOptions
            {
                Title = "Tải chiến lược XAUPY", AllowMultiple = false, FileTypeFilter = [StrategyJson]
            });
            if (files.Count == 0) return;
            await using var stream = await files[0].OpenReadAsync();
            using var document = await JsonDocument.ParseAsync(stream);
            var validation = await supervisor.ValidateConfigAsync(document.RootElement);
            if (!validation.Valid || validation.Profile is null)
                throw new InvalidDataException(string.Join(" • ", validation.Errors));
            if (!await ConfirmApplyAsync(files[0].Name, validation.Profile.Value))
            {
                ShowAction("Đã hủy áp dụng. Cấu hình đang chạy được giữ nguyên.", Brushes.LightGray);
                return;
            }
            var result = await supervisor.ApplyActiveConfigAsync(validation.Profile.Value);
            if (!result.Applied)
                throw new InvalidDataException(string.Join(" • ", result.Errors));
            SetStrategyControls(System.Text.Json.Nodes.JsonNode.Parse(validation.Profile.Value.GetRawText())!.AsObject(), true);
            ShowAction($"Đã xác thực và áp dụng {files[0].Name}. Quyền giao dịch giữ theo lựa chọn người dùng.", Brushes.LightGreen);
        });
    }

    private async Task RunActionAsync(Func<EngineProcessSupervisor, Task> action)
    {
        if (_actionBusy) return;
        _actionBusy = true;
        foreach (var control in _strategyFields.Values) control.IsEnabled = false;
        foreach (var name in new[] { "SaveStrategyButton", "LoadStrategyButton", "ExportStrategyButton" })
            this.FindControl<Button>(name)!.IsEnabled = false;
        try
        {
            if (_supervisor is null || _supervisor.State != EngineConnectionState.Ready)
                throw new InvalidOperationException("Python Engine chưa sẵn sàng. Hãy kết nối lại trước khi thao tác cấu hình.");
            await action(_supervisor);
        }
        catch (Exception ex)
        {
            ShowAction(ex.Message, Brushes.Gold);
        }
        finally
        {
            _actionBusy = false;
            foreach (var control in _strategyFields.Values) control.IsEnabled = _strategyBaseline is not null;
            foreach (var name in new[] { "SaveStrategyButton", "LoadStrategyButton", "ExportStrategyButton" })
                this.FindControl<Button>(name)!.IsEnabled = true;
        }
    }

    private void ShowAction(string message, IBrush foreground)
    {
        var status = Text("StrategyActionText");
        status.Text = message;
        status.Foreground = foreground;
        status.IsVisible = true;
    }

    private async Task<bool> ConfirmApplyAsync(string fileName, JsonElement profile)
    {
        if (TopLevel.GetTopLevel(this) is not Window owner) return false;
        static string Read(JsonElement root, string group, string key) =>
            root.TryGetProperty(group, out var section) && section.TryGetProperty(key, out var value) ? value.ToString() : "—";
        bool accepted = false;
        var dialog = new Window
        {
            Title = "Áp dụng chiến lược", Width = 530, Height = 285, CanResize = false,
            WindowStartupLocation = WindowStartupLocation.CenterOwner, Background = new SolidColorBrush(Color.Parse("#031426"))
        };
        var cancel = new Button { [LocalizationService.TextProperty] = "Hủy", Classes = { "secondary" } };
        var apply = new Button { [LocalizationService.TextProperty] = "Áp dụng cấu hình", Classes = { "primary" } };
        cancel.Click += (_, _) => dialog.Close();
        apply.Click += (_, _) => { accepted = true; dialog.Close(); };
        dialog.Content = new StackPanel
        {
            Margin = new Avalonia.Thickness(20), Spacing = 12,
            Children =
            {
                new TextBlock { Text = $"Áp dụng {fileName}?", [AppearanceService.BaseFontSizeProperty] = 19d, FontWeight = FontWeight.SemiBold, TextWrapping = TextWrapping.Wrap },
                new TextBlock { Text = $"Hồ sơ: {Read(profile, "profile", "name")}\nKhung: {Read(profile, "timeframes", "direction")} → {Read(profile, "timeframes", "pullback")} → {Read(profile, "timeframes", "trigger")}\nRisk mỗi lệnh: {Read(profile, "risk", "risk_percent")}% · Max lot: {Read(profile, "risk", "max_lot")}", TextWrapping = TextWrapping.Wrap },
                new TextBlock { [LocalizationService.TextProperty] = "Chiến lược sẽ tính lại trạng thái từ cấu hình mới. Quyền giao dịch giữ theo lựa chọn hiện tại.", Foreground = Brushes.Gold, TextWrapping = TextWrapping.Wrap },
                new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, Spacing = 8, Children = { cancel, apply } }
            }
        };
        await dialog.ShowDialog(owner);
        return accepted;
    }

    public void Apply(StrategySnapshot strategy, ConfigurationSummary config)
    {
        RefreshStrategyEditor(strategy.ProfileHash);
        Text("IntrabarObservationText").Text = strategy.Intrabar.Mode == "CLOSED_BAR"
            ? "Đang đánh giá nến đóng. Bỏ chọn xác nhận nến đóng để ghi nhận RSI/Z theo tick."
            : $"Theo tick: {strategy.Intrabar.ObservedTicks:N0} quan sát • Cực trị RSI {Format(strategy.Intrabar.RsiExtreme)} / Z {Format(strategy.Intrabar.ZExtreme)}\n{strategy.Intrabar.Reason}";
        Text("StrategyStateText").Text = strategy.Available && strategy.Ready ? "ĐANG HOẠT ĐỘNG" : "ĐANG CHỜ";
        ToolTip.SetTip(Text("StrategyStateText"), strategy.State);
        Text("StrategyStateText").Foreground = strategy.Available && strategy.Ready ? Brushes.MediumSpringGreen : Brushes.Gold;
        Text("BlockedReasonText").Text = strategy.BlockedReason ?? "Không bị block";
        Text("ProfileText").Text = strategy.ProfileName;
        Text("ProfileHashText").Text = string.IsNullOrWhiteSpace(strategy.ProfileHash)
            ? "Hash: —"
            : $"Hash: {strategy.ProfileHash[..Math.Min(12, strategy.ProfileHash.Length)]}";
        Text("DirectionText").Text = strategy.Direction;
        Text("DirectionText").Foreground = DirectionBrush(strategy.Direction);
        Text("DirectionArrow").Text = strategy.Direction switch { "BUY" => "↑", "SELL" => "↓", "BOTH" => "↕", _ => "—" };
        Text("DirectionArrow").Foreground = DirectionBrush(strategy.Direction);
        Text("DirectionDot").Foreground = DirectionBrush(strategy.Direction);
        Text("PullbackDot").Foreground = strategy.ArmedSide is not null ? Brushes.MediumSpringGreen : Brushes.SlateGray;
        Text("TriggerDot").Foreground = strategy.TriggerPassed == true ? Brushes.MediumSpringGreen : Brushes.SlateGray;
        Text("AdxConditionText").Text = Format(strategy.Filters.Adx);
        Text("AtrConditionText").Text = Format(strategy.Filters.Atr);
        Text("AllConditionText").Text = strategy.Available && strategy.Ready &&
            strategy.State.StartsWith("TRIGGERED_", StringComparison.Ordinal) ? "ĐẠT" : "ĐANG CHỜ";
        Text("PullbackRsiMirror").Text = Format(strategy.LivePullback.Rsi);
        Text("TriggerRsiMirror").Text = Format(strategy.LiveTrigger.Rsi);
        Text("PullbackZFilterMirror").Text = Format(strategy.LivePullback.Z);
        Text("TriggerZFilterMirror").Text = Format(strategy.LiveTrigger.Z);
        Text("PullbackConditionMirror").Text = PullbackEvidence(strategy);
        Text("TriggerConditionMirror").Text = Flag(strategy.TriggerPassed);
        Text("ArmedSideText").Text = $"Armed: {strategy.ArmedSide ?? "—"}";

        Text("DirectionTfText").Text = strategy.DirectionTimeframe;
        Text("PullbackTfText").Text = strategy.PullbackTimeframe;
        Text("TriggerTfText").Text = strategy.TriggerTimeframe;
        Text("DirectionRuleText").Text = config.DirectionRuleSummary;
        Text("DirectionMaText").Text = $"MA: {Format(strategy.DirectionIndicators.Ma)}";
        Text("DirectionOpenText").Text = $"Open ref: {Format(strategy.DirectionIndicators.OpenReference)}";
        Text("PullbackRsiText").Text = $"RSI: {Format(strategy.LivePullback.Rsi)}";
        Text("PullbackZText").Text = $"Z: {Format(strategy.LivePullback.Z)}";
        Text("PullbackConditionText").Text =
            $"BUY {Flag(strategy.PullbackBuyPassed)} • SELL {Flag(strategy.PullbackSellPassed)}";
        Text("TriggerRsiText").Text = $"RSI: {Format(strategy.LiveTrigger.Rsi)}";
        Text("TriggerZText").Text = $"Z: {Format(strategy.LiveTrigger.Z)}";
        Text("TriggerConditionText").Text = $"Reversal: {Flag(strategy.TriggerPassed)}";

        Text("AdxText").Text = Format(strategy.Filters.Adx);
        Text("AtrText").Text = Format(strategy.Filters.Atr);
        Text("OpenFilterText").Text = Format(strategy.Filters.OpenReference);

        string bars = strategy.BarsSeen.Count == 0
            ? "—"
            : string.Join(
                "  ",
                strategy.BarsSeen
                    .OrderBy(item => TimeframeOrder(item.Key))
                    .Select(item => $"{item.Key}:{item.Value}"));
        Text("BarsSeenText").Text = $"Bars: {bars}";
        Text("WarmupText").Text = strategy.WarmupReasons.Count == 0
            ? strategy.Available && strategy.Ready ? "Warm-up: đủ dữ liệu cho các indicator đang bật." : "Warm-up: đang chờ dữ liệu chiến lược."
            : $"Warm-up: {string.Join(" • ", strategy.WarmupReasons)}";
        Text("DataErrorText").Text = string.IsNullOrWhiteSpace(strategy.LastDataError)
            ? "Data error: none"
            : $"Data error: {strategy.LastDataError}";

        Text("SymbolText").Text = strategy.Symbol;
        Text("TimeframeSummaryText").Text =
            $"{strategy.DirectionTimeframe} → {strategy.PullbackTimeframe} → {strategy.TriggerTimeframe}";
        Text("ConfigSummaryText").Text =
            $"Direction {config.DirectionRuleSummary} • BUY={(config.AllowBuy ? "ON" : "OFF")} • SELL={(config.AllowSell ? "ON" : "OFF")}";
        Text("ResetReasonText").Text = strategy.LastResetReason ?? "—";

        Text("DirectionConditionText").Text = strategy.Direction;
        Text("DirectionConditionText").Foreground = DirectionBrush(strategy.Direction);
        Text("PullbackStateText").Text = strategy.ArmedSide is not null
            ? $"ARMED {strategy.ArmedSide}"
            : strategy.State.StartsWith("WAIT_PULLBACK", StringComparison.Ordinal)
                ? "WAIT"
                : PullbackEvidence(strategy);
        Text("TriggerStateText").Text = strategy.State.StartsWith("TRIGGERED_", StringComparison.Ordinal)
            ? strategy.State
            : strategy.ArmedSide is not null ? "WAIT REVERSAL" : "WAIT";
        Text("TriggerStateText").Foreground =
            strategy.State.StartsWith("TRIGGERED_", StringComparison.Ordinal)
                ? Brushes.LightGreen
                : Brushes.LightGray;
        Text("ReadyText").Text = strategy.Available && strategy.Ready ? "YES" : "NO";
        Text("ReadyText").Foreground = strategy.Available && strategy.Ready
            ? Brushes.LightGreen
            : Brushes.Gold;

        Text("SignalSequenceText").Text = $"Sequence: {strategy.SignalSequence}";
        Text("LastSignalText").Text = strategy.LastSignal is null
            ? "Chưa có signal."
            : $"{strategy.LastSignal.Side ?? "?"} • bar {strategy.LastSignal.BarTime?.ToString() ?? "—"} • direction {strategy.LastSignal.Direction ?? "—"}";
    }

    private TextBlock Text(string name) =>
        this.FindControl<TextBlock>(name)
        ?? throw new InvalidOperationException($"Missing StrategyDashboard control: {name}");

    private static string PullbackEvidence(StrategySnapshot strategy)
    {
        if (strategy.PullbackBuyPassed == true)
            return "BUY PASS";
        if (strategy.PullbackSellPassed == true)
            return "SELL PASS";
        if (strategy.PullbackBuyPassed == false || strategy.PullbackSellPassed == false)
            return "NOT READY";
        return "—";
    }

    private static string Flag(bool? value) => value switch
    {
        true => "PASS",
        false => "NO",
        _ => "—"
    };

    private static string Format(double? value) =>
        value.HasValue ? value.Value.ToString("0.###") : "—";

    private static IBrush StateBrush(string state)
    {
        if (state.StartsWith("TRIGGERED_", StringComparison.Ordinal))
            return Brushes.LightGreen;
        if (state.StartsWith("ARMED_", StringComparison.Ordinal))
            return Brushes.LightBlue;
        if (state is "STALE" or "FILTER_BLOCKED")
            return Brushes.Gold;
        return Brushes.LightGray;
    }

    private static IBrush DirectionBrush(string direction) => direction switch
    {
        "BUY" => new SolidColorBrush(Color.Parse("#18E58B")),
        "SELL" => new SolidColorBrush(Color.Parse("#FF415C")),
        "BOTH" => Brushes.LightBlue,
        _ => Brushes.LightGray
    };

    private static int TimeframeOrder(string timeframe) => timeframe switch
    {
        "M1" => 1,
        "M3" => 2,
        "M5" => 3,
        "M15" => 4,
        "M30" => 5,
        "H1" => 6,
        "H2" => 7,
        "H4" => 8,
        _ => 99
    };
}
