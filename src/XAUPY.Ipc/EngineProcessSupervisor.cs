using System.Diagnostics;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;

namespace XAUPY.Ipc;

public enum EngineConnectionState
{
    Stopped,
    Starting,
    Connecting,
    Ready,
    Reconnecting,
    MissingEngine,
    Faulted
}

public sealed record Mt5BridgeStatus(
    bool Connected,
    int? AgeMs,
    string? Symbol,
    bool TerminalConnected,
    string? AccountTradeMode,
    bool ExecutionReady,
    bool ExecutionLocked,
    string GuardianReason,
    int SnapshotsTotal)
{
    public static Mt5BridgeStatus Offline { get; } = new(
        false,
        null,
        null,
        false,
        null,
        false,
        true,
        "TASK003_EXECUTION_LOCKED",
        0);
}

public sealed class EngineStateChangedEventArgs(
    EngineConnectionState state,
    string detail,
    DateTimeOffset? lastHeartbeatUtc,
    Mt5BridgeStatus mt5Bridge,
    OverviewSnapshot overview,
    OrdersPositionsSnapshot ordersPositions,
    ConfigurationSummary configuration,
    StrategySnapshot strategy) : EventArgs
{
    public EngineConnectionState State { get; } = state;
    public string Detail { get; } = detail;
    public DateTimeOffset? LastHeartbeatUtc { get; } = lastHeartbeatUtc;
    public Mt5BridgeStatus Mt5Bridge { get; } = mt5Bridge;
    public OverviewSnapshot Overview { get; } = overview;
    public OrdersPositionsSnapshot OrdersPositions { get; } = ordersPositions;
    public ConfigurationSummary Configuration { get; } = configuration;
    public StrategySnapshot Strategy { get; } = strategy;
}

public sealed class EngineProcessSupervisor : IDisposable
{
    public const int DefaultPort = 39421;
    private const int MaxRestartAttempts = 5;

    private readonly SemaphoreSlim _ioGate = new(1, 1);
    private readonly object _sync = new();
    private CancellationTokenSource? _monitorCts;
    private Task? _monitorTask;
    private Process? _process;
    private TcpClient? _client;
    private StreamReader? _reader;
    private StreamWriter? _writer;
    private bool _stopRequested;
    private bool _disposed;
    private int _restartAttempts;

    public EngineProcessSupervisor(string? enginePath = null, int? port = null)
    {
        EnginePath = enginePath
            ?? Environment.GetEnvironmentVariable("XAUPY_ENGINE_PATH")
            ?? Path.Combine(
                AppContext.BaseDirectory,
                "engine",
                OperatingSystem.IsWindows() ? "xaupy-engine.exe" : "xaupy-engine");

        Port = port ?? ReadPortFromEnvironment() ?? DefaultPort;
    }

    public event EventHandler<EngineStateChangedEventArgs>? StateChanged;

    public string EnginePath { get; }
    public int Port { get; }
    public EngineConnectionState State { get; private set; } = EngineConnectionState.Stopped;
    public DateTimeOffset? LastHeartbeatUtc { get; private set; }
    public Mt5BridgeStatus Mt5Bridge { get; private set; } = Mt5BridgeStatus.Offline;
    public OverviewSnapshot Overview { get; private set; } = OverviewSnapshot.Empty;
    public OrdersPositionsSnapshot OrdersPositions { get; private set; } = OrdersPositionsSnapshot.Empty;
    public ConfigurationSummary Configuration { get; private set; } = ConfigurationSummary.Default;
    public StrategySnapshot Strategy { get; private set; } = StrategySnapshot.Empty;

    public Task StartAsync()
    {
        ThrowIfDisposed();

        lock (_sync)
        {
            if (_monitorTask is { IsCompleted: false })
                return Task.CompletedTask;

            _stopRequested = false;
            _restartAttempts = 0;
            Mt5Bridge = Mt5BridgeStatus.Offline;
            Overview = OverviewSnapshot.Empty;
            OrdersPositions = OrdersPositionsSnapshot.Empty;
            Configuration = ConfigurationSummary.Default;
            Strategy = StrategySnapshot.Empty;

            if (!File.Exists(EnginePath))
            {
                SetState(EngineConnectionState.MissingEngine, $"Không tìm thấy Python Engine: {EnginePath}");
                return Task.CompletedTask;
            }

            _monitorCts?.Dispose();
            _monitorCts = new CancellationTokenSource();

            try
            {
                _process = StartOwnedProcess();
                SetState(EngineConnectionState.Starting, $"Đã khởi động Engine PID {_process.Id}; đang chờ IPC...");
                _monitorTask = Task.Run(() => MonitorLoopAsync(_monitorCts.Token));
            }
            catch (Exception ex)
            {
                SetState(EngineConnectionState.Faulted, $"Không thể khởi động Engine: {ex.Message}");
            }
        }

        return Task.CompletedTask;
    }

    public async Task StopAsync()
    {
        ThrowIfDisposed();
        _stopRequested = true;

        try
        {
            if (State is EngineConnectionState.Ready or EngineConnectionState.Reconnecting)
            {
                var request = ProtocolEnvelope.Create("shutdown", new { reason = "desktop_stop" });
                var response = await SendReceiveAsync(request, TimeSpan.FromSeconds(2), CancellationToken.None);
                if (response.Type != "shutdown_ack")
                    throw new InvalidDataException($"Unexpected shutdown response: {response.Type}");
            }
        }
        catch
        {
        }

        _monitorCts?.Cancel();

        if (_monitorTask is not null)
        {
            try
            {
                await _monitorTask.WaitAsync(TimeSpan.FromSeconds(3));
            }
            catch
            {
            }
        }

        CloseConnection();
        TerminateOwnedProcess();
        Mt5Bridge = Mt5BridgeStatus.Offline;
        Overview = OverviewSnapshot.Empty;
        OrdersPositions = OrdersPositionsSnapshot.Empty;
        Strategy = StrategySnapshot.Empty;
        SetState(EngineConnectionState.Stopped, "Python Engine đã dừng.");
    }

    private async Task MonitorLoopAsync(CancellationToken cancellationToken)
    {
        while (!cancellationToken.IsCancellationRequested && !_stopRequested)
        {
            if (_process is null || _process.HasExited)
            {
                if (_restartAttempts >= MaxRestartAttempts)
                {
                    SetState(
                        EngineConnectionState.Faulted,
                        $"Engine dừng bất thường quá {MaxRestartAttempts} lần; không tự khởi động thêm.");
                    return;
                }

                _restartAttempts++;

                try
                {
                    _process?.Dispose();
                    _process = StartOwnedProcess();
                    Mt5Bridge = Mt5BridgeStatus.Offline;
                    Overview = OverviewSnapshot.Empty;
                    OrdersPositions = OrdersPositionsSnapshot.Empty;
                    Strategy = StrategySnapshot.Empty;
                    SetState(
                        EngineConnectionState.Starting,
                        $"Engine đã tự khởi động lại ({_restartAttempts}/{MaxRestartAttempts}), PID {_process.Id}.");
                }
                catch (Exception ex)
                {
                    SetState(EngineConnectionState.Reconnecting, $"Khởi động lại Engine thất bại: {ex.Message}");
                    await DelaySafeAsync(TimeSpan.FromSeconds(1), cancellationToken);
                    continue;
                }
            }

            try
            {
                SetState(
                    State == EngineConnectionState.Ready
                        ? EngineConnectionState.Reconnecting
                        : EngineConnectionState.Connecting,
                    $"Đang kết nối IPC 127.0.0.1:{Port}...");

                await ConnectAndHandshakeAsync(cancellationToken);
                _restartAttempts = 0;
                SetState(EngineConnectionState.Ready, $"IPC v1 sẵn sàng tại 127.0.0.1:{Port}.");

                while (!cancellationToken.IsCancellationRequested &&
                       !_stopRequested &&
                       _process is { HasExited: false })
                {
                    await Task.Delay(TimeSpan.FromSeconds(2), cancellationToken);

                    var heartbeat = ProtocolEnvelope.Create(
                        "heartbeat",
                        new { component = "desktop", desktop_version = "0.9.0-task009" });

                    var response = await SendReceiveAsync(
                        heartbeat,
                        TimeSpan.FromSeconds(3),
                        cancellationToken);

                    if (response.Type != "heartbeat_ack")
                        throw new InvalidDataException($"Unexpected heartbeat response: {response.Type}");

                    if (!string.Equals(response.RequestId, heartbeat.RequestId, StringComparison.Ordinal))
                        throw new InvalidDataException("Heartbeat response request_id does not match.");

                    RejectUnexpectedExecutionEnable(response);
                    Mt5Bridge = ParseBridgeStatus(response.Payload);
                    Overview = OverviewSnapshot.FromHeartbeatPayload(response.Payload);
                    OrdersPositions = OrdersPositionsSnapshot.FromHeartbeatPayload(response.Payload);
                    Strategy = StrategySnapshot.FromHeartbeatPayload(response.Payload);
                    RejectUnexpectedStrategyExecutionEnable(Strategy);
                    RejectUnexpectedOrdersExecutionEnable(OrdersPositions);

                    LastHeartbeatUtc = DateTimeOffset.UtcNow;
                    SetState(
                        EngineConnectionState.Ready,
                        $"Heartbeat OK • PID {_process.Id} • 127.0.0.1:{Port}",
                        LastHeartbeatUtc);
                }
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception ex)
            {
                CloseConnection();
                Mt5Bridge = Mt5BridgeStatus.Offline;
                Overview = OverviewSnapshot.Empty;
                OrdersPositions = OrdersPositionsSnapshot.Empty;
                Strategy = StrategySnapshot.Empty;

                if (_stopRequested || cancellationToken.IsCancellationRequested)
                    break;

                SetState(EngineConnectionState.Reconnecting, $"IPC mất kết nối: {ex.Message}. Đang thử lại...");
                await DelaySafeAsync(TimeSpan.FromSeconds(1), cancellationToken);
            }
        }
    }

    private async Task ConnectAndHandshakeAsync(CancellationToken cancellationToken)
    {
        CloseConnection();

        var client = new TcpClient();
        using var connectCts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        connectCts.CancelAfter(TimeSpan.FromSeconds(3));

        await client.ConnectAsync(IPAddress.Loopback, Port, connectCts.Token);

        var stream = client.GetStream();
        var utf8 = new UTF8Encoding(encoderShouldEmitUTF8Identifier: false);

        _client = client;
        _reader = new StreamReader(stream, utf8, detectEncodingFromByteOrderMarks: false, bufferSize: 4096, leaveOpen: true);
        _writer = new StreamWriter(stream, utf8, bufferSize: 4096, leaveOpen: true)
        {
            AutoFlush = true,
            NewLine = "\n"
        };

        var hello = ProtocolEnvelope.Create(
            "hello",
            new { component = "desktop", desktop_version = "0.9.0-task009" });

        var response = await SendReceiveAsync(hello, TimeSpan.FromSeconds(3), cancellationToken);

        if (response.Type != "hello_ack")
            throw new InvalidDataException($"Unexpected hello response: {response.Type}");

        if (!string.Equals(response.RequestId, hello.RequestId, StringComparison.Ordinal))
            throw new InvalidDataException("hello_ack request_id does not match.");

        RejectUnexpectedExecutionEnable(response);

        var configRequest = ProtocolEnvelope.Create(
            "config_active_get",
            new { component = "desktop", desktop_version = "0.9.0-task009" });

        var configResponse = await SendReceiveAsync(
            configRequest,
            TimeSpan.FromSeconds(3),
            cancellationToken);

        if (configResponse.Type != "config_active_ack")
            throw new InvalidDataException($"Unexpected active config response: {configResponse.Type}");

        RejectUnexpectedExecutionEnable(configResponse);
        Configuration = ConfigurationSummary.FromConfigDefaultsAck(configResponse.Payload);
    }

    private static void RejectUnexpectedExecutionEnable(ProtocolEnvelope response)
    {
        if (response.Payload.TryGetProperty("trading_enabled", out var trading) &&
            trading.ValueKind == JsonValueKind.True)
        {
            throw new InvalidDataException("Task 009 Engine unexpectedly reported trading_enabled=true.");
        }

        if (response.Payload.TryGetProperty("execution_enabled", out var execution) &&
            execution.ValueKind == JsonValueKind.True)
        {
            throw new InvalidDataException("Task 009 Engine unexpectedly reported execution_enabled=true.");
        }
    }

    private static void RejectUnexpectedStrategyExecutionEnable(StrategySnapshot strategy)
    {
        if (strategy.TradingEnabled || strategy.ExecutionEnabled)
            throw new InvalidDataException("Task 009 strategy projection unexpectedly enabled execution.");
    }

    private static void RejectUnexpectedOrdersExecutionEnable(OrdersPositionsSnapshot orders)
    {
        if (!orders.BrokerExecutionLocked || !orders.SimulationOnly)
            throw new InvalidDataException("Task 009 order-book projection unexpectedly unlocked broker execution.");
    }

    private static Mt5BridgeStatus ParseBridgeStatus(JsonElement payload)
    {
        if (!payload.TryGetProperty("bridge", out var bridge) ||
            bridge.ValueKind != JsonValueKind.Object)
        {
            return Mt5BridgeStatus.Offline;
        }

        bool connected = bridge.TryGetProperty("connected", out var connectedElement) &&
                         connectedElement.ValueKind == JsonValueKind.True;

        int? ageMs = null;
        if (bridge.TryGetProperty("age_ms", out var ageElement) &&
            ageElement.ValueKind == JsonValueKind.Number &&
            ageElement.TryGetInt32(out var parsedAge))
        {
            ageMs = parsedAge;
        }

        string? symbol = GetOptionalString(bridge, "symbol");
        string? tradeMode = GetOptionalString(bridge, "account_trade_mode");
        string guardianReason = GetOptionalString(bridge, "guardian_reason")
            ?? "TASK003_EXECUTION_LOCKED";

        bool terminalConnected = bridge.TryGetProperty("terminal_connected", out var terminalElement) &&
                                 terminalElement.ValueKind == JsonValueKind.True;

        bool executionReady = bridge.TryGetProperty("execution_ready", out var readyElement) &&
                              readyElement.ValueKind == JsonValueKind.True;

        bool executionLocked = !bridge.TryGetProperty("execution_locked", out var lockedElement) ||
                               lockedElement.ValueKind != JsonValueKind.False;

        int snapshots = 0;
        if (bridge.TryGetProperty("snapshots_total", out var countElement) &&
            countElement.ValueKind == JsonValueKind.Number)
        {
            countElement.TryGetInt32(out snapshots);
        }

        if (executionReady || !executionLocked)
            throw new InvalidDataException("Task 008 bridge guardian unexpectedly reported execution ready.");

        return new Mt5BridgeStatus(
            connected,
            ageMs,
            symbol,
            terminalConnected,
            tradeMode,
            false,
            true,
            guardianReason,
            snapshots);
    }

    private static string? GetOptionalString(JsonElement parent, string name)
    {
        return parent.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String
            ? value.GetString()
            : null;
    }

    public async Task<JsonElement> GetConfigSchemaAsync(CancellationToken cancellationToken = default)
    {
        ThrowIfDisposed();
        var response = await SendReceiveAsync(
            ProtocolEnvelope.Create("config_schema_get", new { component = "desktop" }),
            TimeSpan.FromSeconds(3),
            cancellationToken);

        if (response.Type != "config_schema_ack")
            throw new InvalidDataException($"Unexpected config schema response: {response.Type}");

        RejectUnexpectedExecutionEnable(response);

        if (!response.Payload.TryGetProperty("config_schema", out var schema) ||
            schema.ValueKind != JsonValueKind.Object)
        {
            throw new InvalidDataException("Engine config schema response is missing config_schema.");
        }

        return schema.Clone();
    }

    public async Task<JsonElement> GetDefaultConfigAsync(CancellationToken cancellationToken = default)
    {
        ThrowIfDisposed();
        var response = await SendReceiveAsync(
            ProtocolEnvelope.Create("config_defaults_get", new { component = "desktop" }),
            TimeSpan.FromSeconds(3),
            cancellationToken);

        if (response.Type != "config_defaults_ack")
            throw new InvalidDataException($"Unexpected config defaults response: {response.Type}");

        RejectUnexpectedExecutionEnable(response);
        return ExtractProfile(response, "config_defaults_ack");
    }

    public async Task<JsonElement> GetActiveConfigAsync(CancellationToken cancellationToken = default)
    {
        ThrowIfDisposed();
        var response = await SendReceiveAsync(
            ProtocolEnvelope.Create("config_active_get", new { component = "desktop" }),
            TimeSpan.FromSeconds(3),
            cancellationToken);

        if (response.Type != "config_active_ack")
            throw new InvalidDataException($"Unexpected active config response: {response.Type}");

        RejectUnexpectedExecutionEnable(response);
        return ExtractProfile(response, "config_active_ack");
    }

    public async Task<ConfigValidationResult> ValidateConfigAsync(
        JsonElement profile,
        CancellationToken cancellationToken = default)
    {
        ThrowIfDisposed();
        var response = await SendReceiveAsync(
            ProtocolEnvelope.Create("config_validate", new { profile }),
            TimeSpan.FromSeconds(5),
            cancellationToken);

        if (response.Type != "config_validate_ack")
            throw new InvalidDataException($"Unexpected config validation response: {response.Type}");

        RejectUnexpectedExecutionEnable(response);
        return ConfigurationApiParser.ParseValidation(response.Payload);
    }

    public async Task<ConfigApplyResult> ApplyActiveConfigAsync(
        JsonElement profile,
        CancellationToken cancellationToken = default)
    {
        ThrowIfDisposed();
        var response = await SendReceiveAsync(
            ProtocolEnvelope.Create("config_active_set", new { profile }),
            TimeSpan.FromSeconds(5),
            cancellationToken);

        if (response.Type != "config_active_set_ack")
            throw new InvalidDataException($"Unexpected config apply response: {response.Type}");

        RejectUnexpectedExecutionEnable(response);
        var result = ConfigurationApiParser.ParseApply(response.Payload);

        if (result.Applied && result.Profile is { } appliedProfile)
        {
            var wrapper = JsonSerializer.SerializeToElement(new { profile = appliedProfile });
            Configuration = ConfigurationSummary.FromConfigDefaultsAck(wrapper);
            SetState(State, "Active configuration updated and validated.");
        }

        return result;
    }

    public async Task<ManualActionResult> SimulateManualActionAsync(
        string action,
        bool confirmed,
        long? ticket = null,
        double? volume = null,
        double? slPoints = null,
        double? tpPoints = null,
        double? percent = null,
        double? price = null,
        double? sl = null,
        double? tp = null,
        string? intentId = null,
        CancellationToken cancellationToken = default)
    {
        ThrowIfDisposed();

        var payload = new Dictionary<string, object?>
        {
            ["intent_id"] = intentId ?? Guid.NewGuid().ToString(),
            ["action"] = action,
            ["confirmed"] = confirmed
        };

        if (ticket.HasValue) payload["ticket"] = ticket.Value;
        if (volume.HasValue) payload["volume"] = volume.Value;
        if (slPoints.HasValue) payload["sl_points"] = slPoints.Value;
        if (tpPoints.HasValue) payload["tp_points"] = tpPoints.Value;
        if (percent.HasValue) payload["percent"] = percent.Value;
        if (price.HasValue) payload["price"] = price.Value;
        if (sl.HasValue) payload["sl"] = sl.Value;
        if (tp.HasValue) payload["tp"] = tp.Value;

        var response = await SendReceiveAsync(
            ProtocolEnvelope.Create("manual_action_simulate", payload),
            TimeSpan.FromSeconds(3),
            cancellationToken);

        if (response.Type != "manual_action_simulate_ack")
            throw new InvalidDataException($"Unexpected manual simulation response: {response.Type}");

        RejectUnexpectedExecutionEnable(response);
        var result = ManualActionResult.FromAck(response.Payload);

        if (!result.Simulated || result.BrokerMutated ||
            result.TradingEnabled || result.ExecutionEnabled)
        {
            throw new InvalidDataException(
                "Task 009 manual action response violated simulation-only safety.");
        }

        return result;
    }

    private static JsonElement ExtractProfile(ProtocolEnvelope response, string responseName)
    {
        if (!response.Payload.TryGetProperty("profile", out var profile) ||
            profile.ValueKind != JsonValueKind.Object)
        {
            throw new InvalidDataException($"{responseName} is missing profile.");
        }

        return profile.Clone();
    }

    private async Task<ProtocolEnvelope> SendReceiveAsync(
        ProtocolEnvelope request,
        TimeSpan timeout,
        CancellationToken cancellationToken)
    {
        await _ioGate.WaitAsync(cancellationToken);

        try
        {
            if (_writer is null || _reader is null)
                throw new IOException("IPC connection is not available.");

            await _writer.WriteLineAsync(request.ToJson());
            await _writer.FlushAsync(cancellationToken);

            using var responseCts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            responseCts.CancelAfter(timeout);

            var line = await _reader.ReadLineAsync(responseCts.Token);
            if (line is null)
                throw new EndOfStreamException("Python Engine closed the IPC stream.");

            var response = ProtocolEnvelope.Parse(line);

            if (!string.Equals(response.RequestId, request.RequestId, StringComparison.Ordinal))
                throw new InvalidDataException("IPC response request_id does not match its request.");

            return response;
        }
        finally
        {
            _ioGate.Release();
        }
    }

    private Process StartOwnedProcess()
    {
        var startInfo = new ProcessStartInfo
        {
            FileName = EnginePath,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            WorkingDirectory = AppContext.BaseDirectory
        };

        startInfo.ArgumentList.Add("--host");
        startInfo.ArgumentList.Add("127.0.0.1");
        startInfo.ArgumentList.Add("--port");
        startInfo.ArgumentList.Add(Port.ToString());

        var process = Process.Start(startInfo)
            ?? throw new InvalidOperationException("Process.Start returned null.");

        process.OutputDataReceived += (_, _) => { };
        process.ErrorDataReceived += (_, _) => { };
        process.BeginOutputReadLine();
        process.BeginErrorReadLine();
        return process;
    }

    private void CloseConnection()
    {
        try { _writer?.Dispose(); } catch { }
        try { _reader?.Dispose(); } catch { }
        try { _client?.Dispose(); } catch { }

        _writer = null;
        _reader = null;
        _client = null;
    }

    private void TerminateOwnedProcess()
    {
        if (_process is null)
            return;

        try
        {
            if (!_process.HasExited)
            {
                if (!_process.WaitForExit(1500))
                    _process.Kill(entireProcessTree: true);
            }
        }
        catch
        {
        }
        finally
        {
            _process.Dispose();
            _process = null;
        }
    }

    private static async Task DelaySafeAsync(TimeSpan delay, CancellationToken cancellationToken)
    {
        try
        {
            await Task.Delay(delay, cancellationToken);
        }
        catch (OperationCanceledException)
        {
        }
    }

    private void SetState(
        EngineConnectionState state,
        string detail,
        DateTimeOffset? lastHeartbeatUtc = null)
    {
        State = state;
        if (lastHeartbeatUtc.HasValue)
            LastHeartbeatUtc = lastHeartbeatUtc;

        StateChanged?.Invoke(
            this,
            new EngineStateChangedEventArgs(
                state,
                detail,
                LastHeartbeatUtc,
                Mt5Bridge,
                Overview,
                OrdersPositions,
                Configuration,
                Strategy));
    }

    private static int? ReadPortFromEnvironment()
    {
        var value = Environment.GetEnvironmentVariable("XAUPY_ENGINE_PORT");
        return int.TryParse(value, out var port) && port is > 0 and <= 65535 ? port : null;
    }

    private void ThrowIfDisposed()
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
    }

    public void Dispose()
    {
        if (_disposed)
            return;

        _disposed = true;
        _stopRequested = true;
        _monitorCts?.Cancel();
        CloseConnection();
        TerminateOwnedProcess();
        _monitorCts?.Dispose();
        _ioGate.Dispose();
        GC.SuppressFinalize(this);
    }
}
