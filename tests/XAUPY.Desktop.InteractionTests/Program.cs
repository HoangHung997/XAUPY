using Avalonia;
using Avalonia.Controls;
using Avalonia.Headless;
using Avalonia.Interactivity;
using Avalonia.Threading;
using System.Collections;
using System.Net;
using System.Net.Sockets;
using System.Reflection;
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

using var supervisor = new EngineProcessSupervisor(enginePath, port);
var main = new MainWindow(); // Never Show(): the real application's auto-start event must not run.
var editor = main.FindControl<ConfigurationEditor>("ConfigurationEditor")!;
editor.AttachSupervisor(supervisor);
try {
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
