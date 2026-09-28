using Avalonia;
using Avalonia.Controls;
using Avalonia.Headless;
using Avalonia.Interactivity;
using Avalonia.Input;
using Avalonia.Threading;
using Avalonia.VisualTree;
using System.Collections;
using System.Net;
using System.Net.Sockets;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using XAUPY.Desktop;
using XAUPY.Ipc;

if (args.Length != 2 || args[0] != "--engine" || !File.Exists(args[1]))
{
    Console.Error.WriteLine("Usage: XAUPY.Desktop.InteractionTests --engine <packaged-engine-executable>");
    return 2;
}
var enginePath = Path.GetFullPath(args[1]);
using var runtime = new IsolatedRuntime();
var reservation = new TcpListener(IPAddress.Loopback, 0); reservation.Start();
int port = ((IPEndPoint)reservation.LocalEndpoint).Port; reservation.Stop();
runtime.SetEnvironment("XAUPY_ENGINE_PORT", port.ToString());
runtime.SetEnvironment("XAUPY_ENGINE_PATH", enginePath);
AppBuilder.Configure<App>().UseHeadless(new AvaloniaHeadlessPlatformOptions { UseHeadlessDrawing = false }).UseSkia().SetupWithoutStarting();
int assertions = 0, failures = 0;
void Assert(bool valid, string message) { assertions++; if (!valid) failures++; Console.WriteLine((valid ? "PASS " : "FAIL ") + message); }
void PumpUntil(Func<bool> predicate, int seconds = 25) {
    var deadline = DateTime.UtcNow.AddSeconds(seconds);
    while (!predicate()) { Dispatcher.UIThread.RunJobs(); if (DateTime.UtcNow > deadline) throw new TimeoutException("Test condition timed out"); Thread.Sleep(10); }
    Dispatcher.UIThread.RunJobs();
}
void Complete(Task task) { PumpUntil(() => task.IsCompleted); task.GetAwaiter().GetResult(); }
object? Field(object target, string name) => target.GetType().GetField(name, BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(target);
object? Invoke(object target, string name, params object[] values) => target.GetType().GetMethod(name, BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(target, values);
Control EditorControl(ConfigurationEditor editor, string path) {
    foreach (var binding in (IEnumerable)Field(editor, "_fields")!) {
        var descriptor = binding!.GetType().GetProperty("Descriptor")!.GetValue(binding)!;
        if ((string)descriptor.GetType().GetProperty("Path")!.GetValue(descriptor)! == path)
            return (Control)binding.GetType().GetProperty("Editor")!.GetValue(binding)!;
    }
    throw new Exception("Editor field missing: " + path);
}
string DraftName(ConfigurationEditor editor) => ((JsonObject)Field(editor, "_draft")!)["profile"]!["name"]!.GetValue<string>();
Control StrategyControl(StrategyDashboard dashboard, string path) =>
    ((Dictionary<string, Control>)Field(dashboard, "_strategyFields")!)[path];
JsonObject ActiveProfile(EngineProcessSupervisor connection) {
    var task = connection.GetActiveConfigAsync(); Complete(task);
    return JsonNode.Parse(task.Result.GetRawText())!.AsObject();
}
void SetActiveProfile(EngineProcessSupervisor connection, JsonObject profile) {
    var task = connection.ApplyActiveConfigAsync(JsonSerializer.SerializeToElement(profile)); Complete(task);
    Assert(task.Result.Applied, "isolated external profile update accepted");
}
void StrategyAction(StrategyDashboard dashboard, string handler) {
    Invoke(dashboard, handler, dashboard, new RoutedEventArgs(Button.ClickEvent));
    PumpUntil(() => !(bool)Field(dashboard, "_actionBusy")!);
}

using var supervisor = new EngineProcessSupervisor(enginePath, port);
var main = new MainWindow(); // Never Show(): the real application's auto-start event must not run.
var editor = main.FindControl<ConfigurationEditor>("ConfigurationEditor")!;
editor.AttachSupervisor(supervisor);
try {
    // Reconnection must clear an automatic stale warning, and warm-up readiness
    // must never be presented as all entry conditions passing.
    var orderStatus = new OrdersPositionsDashboard();
    var multiBook = OrdersPositionsSnapshot.Empty with { Available = true, TerminalConnected = true, AccountTradeMode = "DEMO", Symbol = "XAUUSD", PositionsCount = 2,
        Positions = new[] { new PositionSnapshot(1, 991188, "XAUUSD", "BUY", .01, 4200, 4201, 4190, 4210, 1, 0, 1700000000, "fixture"), new PositionSnapshot(2, 991188, "EURUSD", "BUY", .01, 1, 1.1, .9, 1.2, 1, 0, 1700000000, "fixture") },
        Deals = new[] { new DealSnapshot(3, 1, 991188, "XAUUSD", "SELL", "OUT", .01, 4200, 4201, 1, 0, 0, 1, "TP", 1700000000, "fixture"), new DealSnapshot(4, 2, 991188, "EURUSD", "SELL", "OUT", .01, 1, 1.1, 1, 0, 0, 1, "TP", 1700000000, "fixture") } };
    orderStatus.Apply(multiBook, OverviewSnapshot.Empty, Mt5BridgeStatus.Offline, ConfigurationSummary.Default);
    var allSymbols = orderStatus.FindControl<CheckBox>("ShowAllSymbolsCheck")!;
    allSymbols.IsChecked = false; allSymbols.RaiseEvent(new RoutedEventArgs(CheckBox.ClickEvent));
    Assert(orderStatus.FindControl<StackPanel>("PositionsRowsHost")!.Children.Count == 1, "symbol filter changes position rows immediately without waiting for heartbeat");
    allSymbols.IsChecked = true; allSymbols.RaiseEvent(new RoutedEventArgs(CheckBox.ClickEvent));
    Assert(orderStatus.FindControl<StackPanel>("PositionsRowsHost")!.Children.Count == 2, "all symbols restores both XAUPY positions");
    Assert(orderStatus.FindControl<StackPanel>("DealsRowsHost")!.Children.Count == 1, "history defaults to current symbol");
    var historySymbol = orderStatus.FindControl<CheckBox>("CurrentSymbolHistoryCheck")!;
    historySymbol.IsChecked = false; historySymbol.RaiseEvent(new RoutedEventArgs(CheckBox.ClickEvent));
    Assert(orderStatus.FindControl<StackPanel>("DealsRowsHost")!.Children.Count == 2, "history checkbox reveals other XAUPY symbols");
    orderStatus.ApplyDemoOnceStatus(DemoOnceSnapshot.Disabled with { HasReport = true, IsFresh = true, State = "ARMED", LastBlocker = "SESSION_TIME_BLOCKED" });
    Assert(orderStatus.FindControl<TextBlock>("DemoOnceMessage")!.Text == "SESSION_TIME_BLOCKED", "heartbeat updates current entry blocker");
    orderStatus.ApplyDemoOnceStatus(DemoOnceSnapshot.Disabled with { HasReport = true, IsFresh = true, State = "SUSPENDED", Reason = "PROFILE_CHANGED", LastBlocker = "SESSION_TIME_BLOCKED" });
    Assert(orderStatus.FindControl<TextBlock>("DemoOnceMessage")!.Text == "PROFILE_CHANGED", "suspension reason replaces stale waiting blocker");
    orderStatus.Apply(OrdersPositionsSnapshot.Empty, OverviewSnapshot.Empty, Mt5BridgeStatus.Offline, ConfigurationSummary.Default);
    Assert(orderStatus.FindControl<TextBlock>("ActionStatusText")!.Text!.StartsWith("SIMULATION BLOCKED"),
        "orders show an automatic blocked message while MT5 data is unavailable");
    orderStatus.Apply(OrdersPositionsSnapshot.Empty with { Available = true, TerminalConnected = true, AccountTradeMode = "DEMO" },
        OverviewSnapshot.Empty, Mt5BridgeStatus.Offline, ConfigurationSummary.Default);
    Assert(!orderStatus.FindControl<TextBlock>("ActionStatusText")!.Text!.StartsWith("SIMULATION BLOCKED"),
        "fresh connected demo snapshot clears only the obsolete automatic blocked message");
    Assert(orderStatus.FindControl<Border>("DemoOnceStatusPanel")!.IsVisible && !orderStatus.FindControl<Button>("DemoOnceStart")!.IsEnabled,
        "native demo controls are visible but cannot start without verified engine context");
    var demoReport = DemoOnceSnapshot.FromHeartbeatPayload(JsonSerializer.SerializeToElement(new
    {
        demo_once = new { state = "ARMED", attempt_id = "6db89d49-7333-43b0-b656-9a5c04bc1c68", volume = .01 }
    }));
    orderStatus.ApplyDemoOnceStatus(demoReport);
    var orderStatusWindow = new Window { Content = orderStatus, Width = 1644, Height = 794 };
    orderStatusWindow.Show(); Dispatcher.UIThread.RunJobs();
    try {
        var demoPanel = orderStatus.FindControl<Border>("DemoOnceStatusPanel")!;
        var demoText = orderStatus.FindControl<TextBlock>("DemoOnceStatusText")!;
        var statusOrigin = demoText.TranslatePoint(default, orderStatusWindow)!.Value;
        Assert(demoPanel.IsVisible && demoText.Text!.Contains("CHỜ TÍN HIỆU") &&
            demoText.Bounds.Width > 0 && statusOrigin.Y >= 0 && statusOrigin.Y + demoText.Bounds.Height <= orderStatusWindow.Bounds.Height,
            "armed one-shot status is arranged visibly in its separate Orders panel");
        Assert(orderStatus.FindControl<TextBlock>("ActionStatusText")!.Text!.Contains("mô phỏng") &&
            orderStatus.FindControl<CheckBox>("ManualConfirmCheck")!.IsChecked != true,
            "one-shot status does not replace manual simulation notice or grant manual confirmation");
        var manualConfirm = orderStatus.FindControl<CheckBox>("ManualConfirmCheck")!;
        var confirmOrigin = manualConfirm.TranslatePoint(default, orderStatusWindow)!.Value;
        Assert(confirmOrigin.Y >= 0 && confirmOrigin.Y + manualConfirm.Bounds.Height <= orderStatusWindow.Bounds.Height + .1,
            "one-shot status panel preserves visibility of manual confirmation in the independent right rail");
        orderStatus.ApplyDemoOnceStatus(demoReport with { State = "UNKNOWN", Reason = "RECONCILIATION_REQUIRED" });
        Assert(demoText.Text!.Contains("CẦN KIỂM TRA") && !demoText.Text.Contains("ĐÃ KHỚP"),
            "uncertain one-shot result never presents a confirmed fill");
        orderStatus.ApplyDemoOnceStatus(demoReport.AsStale());
        Assert(demoText.Text!.Contains("MẤT KẾT NỐI") && ToolTip.GetTip(demoPanel)!.ToString()!.Contains("ARMED"),
            "lost IPC makes one-shot freshness explicit while retaining last reported state");
        Invoke(main, "ApplyDemoOnceStatus", demoReport);
        Assert(main.FindControl<TextBlock>("GuardianReasonValue")!.Text!.StartsWith("LOCKED", StringComparison.Ordinal),
            "sidebar one-shot status retains the general execution lock");
        orderStatus.ApplyDemoOnceStatus(DemoOnceSnapshot.Disabled);
        Assert(demoPanel.IsVisible && demoText.Text!.Contains("CHƯA BẮT ĐẦU"), "disabled report leaves native start controls available for an explicit user action");
    }
    finally { orderStatusWindow.Close(); }
    var statusStrategy = new StrategyDashboard();
    statusStrategy.Apply(StrategySnapshot.Empty with { Available = true, Ready = true, State = "WAIT_PULLBACK_SELL" }, ConfigurationSummary.Default);
    Assert(statusStrategy.FindControl<TextBlock>("AllConditionText")!.Text == "ĐANG CHỜ",
        "warm indicators while waiting for pullback do not imply entry conditions passed");
    statusStrategy.Apply(StrategySnapshot.Empty with { Available = true, Ready = true, State = "TRIGGERED_SELL" }, ConfigurationSummary.Default);
    Assert(statusStrategy.FindControl<TextBlock>("AllConditionText")!.Text == "ĐẠT",
        "all-condition badge follows an actual triggered strategy state");
    var monitor = new MonitoringDashboard();
    var observedStrategy = StrategySnapshot.Empty with {
        Available = true, Ready = true, State = "WAIT_PULLBACK_SELL", Direction = "SELL",
        PullbackIndicators = new OscillatorIndicatorSnapshot("M5", 67, 2.4),
        TriggerIndicators = new OscillatorIndicatorSnapshot("M1", 61, .7),
        Filters = new StrategyFilterSnapshot(28, 1.8, null)
    };
    monitor.Apply(observedStrategy, OverviewSnapshot.Empty, Mt5BridgeStatus.Offline, ConfigurationSummary.Default);
    var matrix = monitor.FindControl<Grid>("MonitorConditionMatrix")!;
    string Cell(int row, int column) => ((TextBlock)((Border)matrix.Children.Single(c => Grid.GetRow(c) == row && Grid.GetColumn(c) == column)).Child!).Text!;
    Assert(matrix.RowDefinitions.Count == 8 && Cell(7, 0) == "D1" && Enumerable.Range(1, 3).All(column => Cell(7, column) == "—"),
        "Monitoring seven-frame matrix leaves unevaluated D1 conditions unavailable");
    monitor.Apply(observedStrategy with { DirectionTimeframe = "H2", PullbackTimeframe = "M3" }, OverviewSnapshot.Empty, Mt5BridgeStatus.Offline, ConfigurationSummary.Default);
    var monitorWindow = new Window { Content = monitor, Width = 1342, Height = 794 };
    monitorWindow.Show(); Dispatcher.UIThread.RunJobs();
    try {
        var matrixScroll = matrix.GetVisualAncestors().OfType<ScrollViewer>().First();
        matrixScroll.Offset = new Vector(0, 999); Dispatcher.UIThread.RunJobs();
        Assert(matrix.RowDefinitions.Count == 10 && Enumerable.Range(1, 9).Any(row => Cell(row, 0) == "M3")
            && Enumerable.Range(1, 9).Any(row => Cell(row, 0) == "H2") && matrixScroll.Offset.Y > 0,
            "Monitoring adds real M3/H2 roles and scrolls all nine timeframe rows within the card");
        Assert(monitor.FindControl<ReferenceGauge>("MonitorZGauge")!.Value == 2.4
            && monitor.FindControl<ReferenceGauge>("MonitorRsiGauge")!.Value == 61
            && monitor.FindControl<ReferenceGauge>("MonitorAdxGauge")!.Value == 28
            && monitor.FindControl<ReferenceGauge>("MonitorAtrGauge")!.Value == 1.8,
            "Monitoring gauges reflect supplied strategy metrics rather than readiness or placeholder values");
    }
    finally { monitorWindow.Close(); }
    var direction = main.FindControl<ComboBox>("QuickDirection")!;
    var apply = main.FindControl<Button>("QuickApply")!;
    Assert(direction.SelectedItem?.ToString() == "M30", "quick controls initialize from canonical baseline");
    direction.SelectedItem = "H1"; Dispatcher.UIThread.RunJobs();
    Assert((bool)Field(main, "_quickConfigurationDirty")!, "real ComboBox change marks quick configuration dirty");
    Invoke(main, "UpdateQuickConfiguration", ConfigurationSummary.Default);
    Assert(direction.SelectedItem?.ToString() == "H1", "heartbeat keeps edited quick selection");
    direction.SelectedItem = "M30"; Dispatcher.UIThread.RunJobs();
    Assert(!(bool)Field(main, "_quickConfigurationDirty")!, "reverting ComboBox clears quick dirty flag");
    Assert(apply.Content?.ToString() == "Áp dụng cấu hình nhanh", "revert restores quick button label");
    var allowBuy = main.FindControl<CheckBox>("QuickAllowBuy")!;
    bool baselineBuy = allowBuy.IsChecked == true;
    allowBuy.IsChecked = !baselineBuy;
    Assert((bool)Field(main, "_quickConfigurationDirty")!, "real buy checkbox marks quick dirty flag");
    allowBuy.IsChecked = baselineBuy;
    Assert(!(bool)Field(main, "_quickConfigurationDirty")!, "reverting checkbox clears quick dirty flag");

    Complete(supervisor.StartAsync()); PumpUntil(() => supervisor.State == EngineConnectionState.Ready);
    Assert(!supervisor.Mt5Bridge.Connected, "isolated engine has no live MT5 connection");
    var initialLoad = editor.EnsureLoadedAsync();
    var simultaneousLoad = editor.EnsureLoadedAsync();
    var shortcutDuringLoad = editor.OpenShortcutAsync("timeframes");
    Assert(ReferenceEquals(initialLoad, simultaneousLoad), "parallel navigation and shortcut share one load Task");
    Complete(Task.WhenAll(initialLoad, simultaneousLoad, shortcutDuringLoad));
    Assert(((IList)Field(editor, "_fields")!).Count == 133, "actual isolated IPC loads all 133 schema controls");
    Assert(!editor.HasUnsavedChanges, "initial actual schema/profile load is clean after queued UI events");
    var name = (TextBox)EditorControl(editor, "profile.name");
    name.Text = "TEST ONLY UNSAVED DRAFT"; Dispatcher.UIThread.RunJobs();
    Assert(editor.HasUnsavedChanges && DraftName(editor) == "TEST ONLY UNSAVED DRAFT", "real full editor TextBox updates unsaved draft");
    direction.SelectedItem = "H1";
    apply.RaiseEvent(new RoutedEventArgs(Button.ClickEvent)); Dispatcher.UIThread.RunJobs();
    Assert(apply.Content?.ToString() == "Chưa áp dụng" && apply.IsEnabled, "QuickApply dirty guard blocks and re-enables button");
    Assert(ToolTip.GetTip(apply)?.ToString()?.Contains("chưa áp dụng") == true, "QuickApply explains how to preserve the full draft");
    Assert(DraftName(editor) == "TEST ONLY UNSAVED DRAFT" && editor.HasUnsavedChanges, "QuickApply does not discard full editor draft");
    Complete(editor.OpenShortcutAsync("timeframes"));
    Assert(DraftName(editor) == "TEST ONLY UNSAVED DRAFT" && editor.HasUnsavedChanges, "configuration shortcut preserves loaded full draft");

    Complete(supervisor.StopAsync());
    Complete(editor.NotifyEngineStateAsync(EngineConnectionState.Stopped));
    Complete(supervisor.StartAsync()); PumpUntil(() => supervisor.State == EngineConnectionState.Ready);
    Complete(editor.NotifyEngineStateAsync(EngineConnectionState.Ready));
    Assert(DraftName(editor) == "TEST ONLY UNSAVED DRAFT" && editor.HasUnsavedChanges, "actual isolated engine restart preserves unsaved full draft");
    Assert(((TextBox)EditorControl(editor, "profile.name")).Text == "TEST ONLY UNSAVED DRAFT", "rebuilt schema controls retain visible draft after reconnect");
    var active = supervisor.GetActiveConfigAsync(); Complete(active);
    Assert(active.Result.GetProperty("profile").GetProperty("name").GetString() != "TEST ONLY UNSAVED DRAFT", "unsaved draft never reaches persisted engine profile");
    Assert(!File.Exists(Path.Combine(runtime.Root, "state", "runtime-v1.json")), "test makes no persisted profile or settings mutations");

    Invoke(editor, "ReloadActive_OnClick", editor, new RoutedEventArgs(Button.ClickEvent));
    PumpUntil(() => !editor.HasUnsavedChanges && !(bool)Field(editor, "_loading")!);
    var mainStrategy = main.FindControl<StrategyDashboard>("StrategyDashboard")!;
    mainStrategy.AttachSupervisor(supervisor);
    mainStrategy.Apply(supervisor.Strategy, supervisor.Configuration);
    PumpUntil(() => Field(mainStrategy, "_strategyBaseline") is not null && Field(mainStrategy, "_strategyLoad") is Task { IsCompleted: true });
    var mainZLevel = (NumericUpDown)StrategyControl(mainStrategy, "pullback.z_sell_level");
    var mainZBaseline = mainZLevel.Value;
    mainZLevel.Value += .1m;
    apply.RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
    Dispatcher.UIThread.RunJobs();
    Assert(ToolTip.GetTip(apply)?.ToString()?.Contains("Tab Chiến lược") == true && apply.IsEnabled,
        "Overview QuickApply guards a real Strategy draft after full editor is clean");
    Assert(mainStrategy.HasUnsavedChanges && mainZLevel.Value == mainZBaseline + .1m,
        "Overview conflicting apply preserves the real Strategy draft");
    mainZLevel.Value = mainZBaseline;

    // The following save/conflict tests intentionally persist ONLY inside the
    // isolated temporary runtime, using a real engine and real Avalonia controls.
    var strategy = new StrategyDashboard();
    strategy.AttachSupervisor(supervisor);
    strategy.Apply(supervisor.Strategy, supervisor.Configuration);
    PumpUntil(() => Field(strategy, "_strategyBaseline") is not null && Field(strategy, "_strategyLoad") is Task { IsCompleted: true });
    Assert(!strategy.HasUnsavedChanges, "Strategy initial profile load remains clean after queued UI events");
    var zLevel = (NumericUpDown)StrategyControl(strategy, "pullback.z_sell_level");
    var rsiLevel = (NumericUpDown)StrategyControl(strategy, "pullback.rsi_buy_level");
    var strategyDirection = (ComboBox)StrategyControl(strategy, "timeframes.direction");
    var closedBar = (CheckBox)StrategyControl(strategy, "trigger.confirm_closed_bar");
    var sessionStart = (TextBox)StrategyControl(strategy, "sessions.session1_start");
    decimal originalZ = zLevel.Value!.Value;
    Assert(zLevel.IsEnabled && rsiLevel.IsEnabled && strategyDirection.IsEnabled, "Strategy editable fields enable after actual IPC load");
    zLevel.Value = originalZ + .5m;
    Assert(strategy.HasUnsavedChanges, "Strategy numeric edit marks its own draft dirty");
    strategy.Apply(supervisor.Strategy, supervisor.Configuration);
    Dispatcher.UIThread.RunJobs();
    Assert(strategy.HasUnsavedChanges && zLevel.Value == originalZ + .5m, "Strategy heartbeat preserves numeric draft");
    Complete(supervisor.StopAsync());
    strategy.Apply(StrategySnapshot.Empty, ConfigurationSummary.Default);
    Complete(supervisor.StartAsync()); PumpUntil(() => supervisor.State == EngineConnectionState.Ready);
    strategy.Apply(supervisor.Strategy, supervisor.Configuration);
    Dispatcher.UIThread.RunJobs();
    Assert(strategy.HasUnsavedChanges && zLevel.Value == originalZ + .5m, "Strategy draft survives actual isolated engine restart");
    Assert(ActiveProfile(supervisor)["pullback"]!["z_sell_level"]!.GetValue<double>() == (double)originalZ,
        "Strategy draft remains unapplied after restart");
    zLevel.Value = originalZ;
    Assert(!strategy.HasUnsavedChanges, "Strategy numeric revert restores clean baseline");
    var originalDirection = strategyDirection.SelectedItem;
    strategyDirection.SelectedItem = "H1";
    Assert(strategy.HasUnsavedChanges, "Strategy timeframe ComboBox edit marks dirty");
    strategyDirection.SelectedItem = originalDirection;
    Assert(!strategy.HasUnsavedChanges, "Strategy timeframe ComboBox revert clears dirty");
    bool? originalClosed = closedBar.IsChecked;
    closedBar.IsChecked = !originalClosed;
    Assert(strategy.HasUnsavedChanges, "Strategy confirmation mode CheckBox edit marks dirty");
    closedBar.IsChecked = originalClosed;
    Assert(!strategy.HasUnsavedChanges, "Strategy confirmation mode revert clears dirty");
    string? originalSession = sessionStart.Text;
    sessionStart.Text = "12:34"; Dispatcher.UIThread.RunJobs();
    Assert(strategy.HasUnsavedChanges, "Strategy session TextBox edit marks dirty");
    sessionStart.Text = originalSession; Dispatcher.UIThread.RunJobs();
    Assert(!strategy.HasUnsavedChanges, "Strategy session TextBox revert clears dirty");

    zLevel.Value = originalZ + .5m;
    strategy.HasConflictingDraft = () => true;
    StrategyAction(strategy, "ApplyStrategy_OnClick");
    Assert(strategy.HasUnsavedChanges && zLevel.Value == originalZ + .5m,
        "Strategy cross-tab draft guard retains unsaved values");
    Assert(strategy.FindControl<TextBlock>("StrategyActionText")!.Text!.Contains("bản nháp"),
        "Strategy cross-tab conflict reports actionable reason");
    Assert(ActiveProfile(supervisor)["pullback"]!["z_sell_level"]!.GetValue<double>() == (double)originalZ,
        "Strategy cross-tab conflict cannot mutate active profile");
    strategy.HasConflictingDraft = () => false;

    var conflicting = ActiveProfile(supervisor);
    conflicting["pullback"]!["z_sell_level"] = (double)(originalZ + .8m);
    SetActiveProfile(supervisor, conflicting);
    StrategyAction(strategy, "ApplyStrategy_OnClick");
    Assert(strategy.HasUnsavedChanges && zLevel.Value == originalZ + .5m,
        "Strategy same-field external conflict preserves local draft");
    Assert(strategy.FindControl<TextBlock>("StrategyActionText")!.Text!.Contains("đã thay đổi"),
        "Strategy same-field external conflict explains reload requirement");
    Assert(ActiveProfile(supervisor)["pullback"]!["z_sell_level"]!.GetValue<double>() == (double)(originalZ + .8m),
        "Strategy same-field conflict cannot overwrite newer active value");
    StrategyAction(strategy, "ResetStrategyDraft_OnClick");
    Assert(!strategy.HasUnsavedChanges && zLevel.Value == originalZ + .8m,
        "Strategy explicit reload discards draft and adopts newer baseline");

    decimal mergedZ = zLevel.Value!.Value + .3m;
    zLevel.Value = mergedZ;
    var independentlyChanged = ActiveProfile(supervisor);
    double mergedRsi = independentlyChanged["pullback"]!["rsi_buy_level"]!.GetValue<double>() + 1;
    independentlyChanged["pullback"]!["rsi_buy_level"] = mergedRsi;
    independentlyChanged["profile"]!["notes"] = "ISOLATED EXTERNAL FIELD MUST SURVIVE";
    SetActiveProfile(supervisor, independentlyChanged);
    StrategyAction(strategy, "ApplyStrategy_OnClick");
    var merged = ActiveProfile(supervisor);
    Assert(!strategy.HasUnsavedChanges && zLevel.Value == mergedZ,
        "Strategy successful Apply establishes a clean saved baseline");
    Assert(merged["pullback"]!["z_sell_level"]!.GetValue<double>() == (double)mergedZ,
        "Strategy Apply persists the locally modified field");
    Assert(merged["pullback"]!["rsi_buy_level"]!.GetValue<double>() == mergedRsi && rsiLevel.Value == (decimal)mergedRsi,
        "Strategy Apply merges and refreshes an externally changed untouched editor field");
    Assert(merged["profile"]!["notes"]!.GetValue<string>() == "ISOLATED EXTERNAL FIELD MUST SURVIVE",
        "Strategy Apply preserves unrelated active-profile fields");
    zLevel.Value = mergedZ + .1m; zLevel.Value = mergedZ;
    Assert(!strategy.HasUnsavedChanges, "Strategy revert compares against the newly saved baseline");
    Complete(supervisor.StopAsync());
    Complete(supervisor.StartAsync()); PumpUntil(() => supervisor.State == EngineConnectionState.Ready);
    var persisted = ActiveProfile(supervisor);
    Assert(persisted["pullback"]!["z_sell_level"]!.GetValue<double>() == (double)mergedZ
        && persisted["pullback"]!["rsi_buy_level"]!.GetValue<double>() == mergedRsi,
        "Strategy merged saved baseline survives actual engine restart");
    Assert(File.Exists(Path.Combine(runtime.Root, "state", "runtime-v1.json")),
        "Strategy save evidence exists exclusively in isolated temporary state");

    var toolsView = new ToolsDashboard(); toolsView.AttachSupervisor(supervisor);
    Complete(toolsView.EnsureLoadedAsync());
    var toolsWindow = new Window { Content = toolsView, Width = 1644, Height = 794 };
    toolsWindow.Show(); Dispatcher.UIThread.RunJobs();
    try {
        var jsonEditor = toolsView.FindControl<TextBox>("ToolEditor")!;
        Assert(jsonEditor.GetVisualDescendants().OfType<JsonSyntaxPresenter>().Any(),
            "Tools uses syntax-colored native TextPresenter inside editable TextBox");
        string originalJson = jsonEditor.Text!;
        var colorSpans = JsonSyntaxPresenter.Tokenize("{\"escaped\\\"key\":\"value\",\"n\":-1.2e+3,\"b\":true,\"x\":null}");
        Assert(colorSpans.Count == 8 && colorSpans.Select(s => s.Brush.ToString()).Distinct().Count() == 5,
            "JSON tokenizer preserves escaped string boundaries and five token colors");
        jsonEditor.Text = "{\n  \"side\": \"SELL\",\n  \"enabled\": true\n}";
        Dispatcher.UIThread.RunJobs(); jsonEditor.Focus();
        var sellIndex = jsonEditor.Text.IndexOf("SELL", StringComparison.Ordinal);
        jsonEditor.CaretIndex = sellIndex + 4; jsonEditor.SelectionStart = sellIndex; jsonEditor.SelectionEnd = sellIndex + 4;
        toolsWindow.KeyTextInput("BUY"); Dispatcher.UIThread.RunJobs();
        Assert(jsonEditor.Text.Contains("\"BUY\"") && !jsonEditor.Text.Contains("SELL"),
            "native editor typing replaces the actual selected JSON range");
        toolsWindow.KeyPress(Key.Z, RawInputModifiers.Control, PhysicalKey.Z, null); toolsWindow.KeyRelease(Key.Z, RawInputModifiers.Control, PhysicalKey.Z, null); Dispatcher.UIThread.RunJobs();
        Assert(jsonEditor.Text.Contains("SELL"), "native editor undo restores selected text replacement");
        toolsWindow.KeyPress(Key.F, RawInputModifiers.Control, PhysicalKey.F, null); toolsWindow.KeyRelease(Key.F, RawInputModifiers.Control, PhysicalKey.F, null); Dispatcher.UIThread.RunJobs();
        Assert(toolsView.FindControl<Grid>("EditorSearchBar")!.IsVisible,
            "Ctrl+F opens the Tools search control through routed keyboard input");
        var search = toolsView.FindControl<TextBox>("EditorSearchText")!;
        search.Text = "enabled"; search.Focus();
        toolsWindow.KeyPress(Key.Enter, RawInputModifiers.None, PhysicalKey.Enter, null); toolsWindow.KeyRelease(Key.Enter, RawInputModifiers.None, PhysicalKey.Enter, null); Dispatcher.UIThread.RunJobs();
        Assert(jsonEditor.SelectedText == "enabled", "Enter in search selects the actual matching editor text");
        jsonEditor.Text = "{\"message\":\"Unicode tiếng Việt\",\"enabled\":true}";
        jsonEditor.Focus(); toolsWindow.KeyPress(Key.F, RawInputModifiers.Control | RawInputModifiers.Shift, PhysicalKey.F, null);
        toolsWindow.KeyRelease(Key.F, RawInputModifiers.Control | RawInputModifiers.Shift, PhysicalKey.F, null); Dispatcher.UIThread.RunJobs();
        Assert(jsonEditor.Text.Contains('\n') && JsonNode.Parse(jsonEditor.Text)!["message"]!.GetValue<string>() == "Unicode tiếng Việt",
            "Ctrl+Shift+F formats editable JSON without changing Unicode values");
        toolsWindow.KeyPress(Key.F11, RawInputModifiers.None, PhysicalKey.F11, null); toolsWindow.KeyRelease(Key.F11, RawInputModifiers.None, PhysicalKey.F11, null); Dispatcher.UIThread.RunJobs();
        Assert(!toolsView.FindControl<Border>("ToolNavigation")!.IsVisible,
            "F11 expands the actual JSON workspace");
        toolsWindow.KeyPress(Key.F11, RawInputModifiers.None, PhysicalKey.F11, null); toolsWindow.KeyRelease(Key.F11, RawInputModifiers.None, PhysicalKey.F11, null); Dispatcher.UIThread.RunJobs();
        Assert(toolsView.FindControl<Border>("ToolNavigation")!.IsVisible,
            "second F11 restores the tool and help columns");
        jsonEditor.Text = originalJson; Dispatcher.UIThread.RunJobs();
        var editScroll = jsonEditor.GetVisualDescendants().OfType<ScrollViewer>().Single(v => v.Name == "PART_ScrollViewer");
        var gutterScroll = jsonEditor.GetVisualDescendants().OfType<ScrollViewer>().Single(v => v.Name == "PART_GutterScroll");
        editScroll.Offset = new Vector(0, 190); Dispatcher.UIThread.RunJobs();
        Assert(editScroll.Offset.Y > 0 && Math.Abs(editScroll.Offset.Y - gutterScroll.Offset.Y) < .1,
            "native multiline scrolling keeps line-number gutter synchronized");
        var numbers = jsonEditor.GetVisualDescendants().OfType<TextBlock>().Single(v => v.Name == "PART_LineNumbers");
        Assert(numbers.Text!.Split('\n').Length == originalJson.Count(c => c == '\n') + 1,
            "line-number gutter covers every real JSON line");
        var info = toolsView.FindControl<TextBlock>("EditorFileInfo")!;
        Assert(info.Bounds.Height > 0 && info.Bounds.Width > 0, "Tools file information remains arranged beside the real editor");
    }
    finally { toolsWindow.Close(); }
    var beforeToolsAudit = ActiveProfile(supervisor);
    var eurProfile = (JsonObject)beforeToolsAudit.DeepClone(); eurProfile["strategy"]!["symbol"] = "EURUSD";
    SetActiveProfile(supervisor, eurProfile);
    var draftTools = new ToolsDashboard(); draftTools.AttachSupervisor(supervisor); Complete(draftTools.EnsureLoadedAsync());
    Assert(draftTools.FindControl<TextBox>("ToolSymbol")!.Text == "EURUSD", "Tools reads symbol from strategy.symbol");
    var draftEditor = draftTools.FindControl<TextBox>("ToolEditor")!;
    var toolsDraft = (JsonObject)eurProfile.DeepClone(); toolsDraft["profile"]!["name"] = "Unapplied Tools draft";
    draftEditor.Text = toolsDraft.ToJsonString(); Dispatcher.UIThread.RunJobs();
    Complete(draftTools.EnsureLoadedAsync(true));
    Assert(draftTools.HasUnsavedChanges && draftEditor.Text!.Contains("Unapplied Tools draft"), "automatic reload preserves Tools draft");
    var menuButton = draftTools.FindControl<StackPanel>("ToolMenu")!.Children.OfType<Button>().First(b => b.Tag?.ToString() == "compare");
    menuButton.RaiseEvent(new RoutedEventArgs(Button.ClickEvent)); Dispatcher.UIThread.RunJobs();
    Assert(draftEditor.Text!.Contains("Unapplied Tools draft") && Field(draftTools, "_mode")?.ToString() == "editor", "tool switch cannot discard draft without an explicit choice");
    draftTools.HasConflictingDraft = () => true;
    Invoke(draftTools, "Apply_OnClick", draftTools, new RoutedEventArgs()); PumpUntil(() => !(bool)Field(draftTools, "_busy")!);
    Assert(draftTools.HasUnsavedChanges && draftTools.FindControl<TextBlock>("ToolResult")!.Text!.Contains("bản nháp"), "Tools prevents conflicting cross-tab apply");
    draftTools.HasConflictingDraft = () => false;
    SetActiveProfile(supervisor, beforeToolsAudit);
    Invoke(draftTools, "Apply_OnClick", draftTools, new RoutedEventArgs()); PumpUntil(() => !(bool)Field(draftTools, "_busy")!);
    Assert(draftTools.HasUnsavedChanges && draftTools.FindControl<TextBlock>("ToolResult")!.Text!.Contains("đã thay đổi"), "Tools detects concurrent active-profile changes and preserves draft");
    var rangeOptimizer = new OptimizerDashboard();
    var rangesProfile = (JsonObject)beforeToolsAudit.DeepClone(); rangesProfile["stop_loss"]!["mode"] = "ATR"; rangesProfile["take_profit"]!["mode"] = "ZRSI_DYNAMIC";
    rangesProfile["pullback"]!["rsi_enabled"] = true; rangesProfile["pullback"]!["z_enabled"] = true;
    rangesProfile["trigger"]!["rsi_enabled"] = true; rangesProfile["trigger"]!["z_enabled"] = true;
    Invoke(rangeOptimizer, "InitializeRangesFromActiveProfile", JsonSerializer.SerializeToElement(rangesProfile));
    var rangeList = (List<Dictionary<string, object>>)Invoke(rangeOptimizer, "BuildParameterRanges")!;
    var paths = rangeList.Select(r => r["path"].ToString()).ToArray();
    Assert(rangeOptimizer.FindControl<TextBox>("SlMinBox")!.IsEnabled && paths.Contains("stop_loss.atr_multiplier"), "ATR multiplier is an active optimizer range");
    Assert(rangeOptimizer.FindControl<TextBox>("TpMinBox")!.IsEnabled && paths.Contains("take_profit.fixed_price_units"), "dynamic TP initial target is an active optimizer range");
    Assert(new[] { "pullback.rsi_period", "trigger.rsi_period", "pullback.z_period", "trigger.z_period", "pullback.z_buy_level", "pullback.z_sell_level", "trigger.rsi_reversal_delta", "trigger.z_reversal_delta" }.All(paths.Contains), "RSI and Z periods, thresholds and both reversal deltas are independently represented");
    ((DispatcherTimer)Field(rangeOptimizer, "_pollTimer")!).Stop();

    var settingsView = new SettingsDashboard(); settingsView.AttachSupervisor(supervisor);
    Complete(settingsView.EnsureLoadedAsync());
    var settingsWindow = new Window { Content = settingsView, Width = 1342, Height = 794 };
    settingsWindow.Show(); Dispatcher.UIThread.RunJobs();
    try {
        var autoEngine = settingsView.FindControl<ToggleSwitch>("AutoEngine")!;
        var autoRestart = settingsView.FindControl<ToggleSwitch>("AutoRestart")!;
        var autoBackup = settingsView.FindControl<ToggleSwitch>("AutoBackup")!;
        Assert(autoEngine.IsChecked == true && autoRestart.IsChecked == true && autoBackup.IsChecked == true,
            "Settings replacement toggles load persisted boolean settings");
        autoEngine.IsChecked = false; autoRestart.IsChecked = false; autoBackup.IsChecked = false;
        string profileBefore = ActiveProfile(supervisor).ToJsonString();
        Invoke(settingsView, "Save_OnClick", settingsView, new RoutedEventArgs(Button.ClickEvent));
        PumpUntil(() => !(bool)Field(settingsView, "_busy")!);
        var savedSettingsTask = supervisor.GetSettingsAsync(); Complete(savedSettingsTask);
        var savedSettings = savedSettingsTask.Result.GetProperty("settings");
        Assert(!savedSettings.GetProperty("startup").GetProperty("auto_start_engine").GetBoolean()
            && !savedSettings.GetProperty("startup").GetProperty("auto_restart_engine").GetBoolean()
            && !savedSettings.GetProperty("backup").GetProperty("auto_backup").GetBoolean(),
            "Settings native switches persist through the actual isolated maintenance API");
        Assert(ActiveProfile(supervisor).ToJsonString() == profileBefore,
            "Settings visual controls do not overwrite the strategy profile");
        Complete(supervisor.StopAsync()); Complete(supervisor.StartAsync()); PumpUntil(() => supervisor.State == EngineConnectionState.Ready);
        Complete(settingsView.EnsureLoadedAsync(true));
        Assert(autoEngine.IsChecked == false && autoRestart.IsChecked == false && autoBackup.IsChecked == false,
            "Settings toggle choices survive an actual isolated Engine restart");
        Assert(!settingsView.GetVisualDescendants().OfType<ScrollViewer>().Any(v => v.Content == settingsView.FindControl<Grid>("SettingsCards")),
            "Settings card rows fit the reference canvas without a clipping outer scroll viewport");
        var cards = settingsView.FindControl<Grid>("SettingsCards")!;
        Assert(cards.Bounds.Height > 600 && cards.Children.All(c => c.Bounds.Bottom <= cards.Bounds.Height + .1),
            "all Settings cards, including backup and recovery, stay inside the arranged canvas");
    }
    finally { settingsWindow.Close(); }
}
finally {
    try { Complete(supervisor.StopAsync()); }
    finally {
        ((DispatcherTimer)Field(main, "_clockTimer")!).Stop();
        ((EngineProcessSupervisor)Field(main, "_engineSupervisor")!).Dispose();
        main.Close();
    }
}
Console.WriteLine($"{assertions - failures}/{assertions} desktop interaction assertions passed; {failures} failures. Engine used an isolated temporary runtime and no MT5 connection.");
return failures == 0 ? 0 : 1;

sealed class IsolatedRuntime : IDisposable
{
    private readonly Dictionary<string, string?> _previousEnvironment = new();
    public string Root { get; } = Directory.CreateTempSubdirectory("xaupy-ui-interactions-").FullName;

    public IsolatedRuntime()
    {
        foreach (var (key, folder) in new[] {
            ("XAUPY_STATE_DIR", "state"), ("XAUPY_LOG_DIR", "logs"),
            ("XAUPY_BACKTEST_DIR", "backtests"), ("XAUPY_OPTIMIZER_DIR", "optimizer") })
            SetEnvironment(key, Path.Combine(Root, folder));
    }

    public void SetEnvironment(string key, string value)
    {
        _previousEnvironment.TryAdd(key, Environment.GetEnvironmentVariable(key));
        Environment.SetEnvironmentVariable(key, value);
    }

    public void Dispose()
    {
        foreach (var item in _previousEnvironment)
            Environment.SetEnvironmentVariable(item.Key, item.Value);
        var directory = new DirectoryInfo(Root);
        var comparison = OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
        if (directory.Exists && directory.LinkTarget is null &&
            directory.Name.StartsWith("xaupy-ui-interactions-", StringComparison.Ordinal) &&
            string.Equals(directory.Parent?.FullName, Path.TrimEndingDirectorySeparator(Path.GetFullPath(Path.GetTempPath())), comparison))
        {
            try { directory.Delete(recursive: true); }
            catch (IOException ex) { Console.Error.WriteLine($"Temporary test cleanup deferred: {ex.Message}"); }
            catch (UnauthorizedAccessException ex) { Console.Error.WriteLine($"Temporary test cleanup deferred: {ex.Message}"); }
        }
    }
}
