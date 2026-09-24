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

public sealed class EngineStateChangedEventArgs(
    EngineConnectionState state,
    string detail,
    DateTimeOffset? lastHeartbeatUtc = null) : EventArgs
{
    public EngineConnectionState State { get; } = state;
    public string Detail { get; } = detail;
    public DateTimeOffset? LastHeartbeatUtc { get; } = lastHeartbeatUtc;
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

    public Task StartAsync()
    {
        ThrowIfDisposed();

        lock (_sync)
        {
            if (_monitorTask is { IsCompleted: false })
                return Task.CompletedTask;

            _stopRequested = false;
            _restartAttempts = 0;

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
                        new { component = "desktop", desktop_version = "0.2.0-task002" });

                    var response = await SendReceiveAsync(
                        heartbeat,
                        TimeSpan.FromSeconds(3),
                        cancellationToken);

                    if (response.Type != "heartbeat_ack")
                        throw new InvalidDataException($"Unexpected heartbeat response: {response.Type}");

                    if (!string.Equals(response.RequestId, heartbeat.RequestId, StringComparison.Ordinal))
                        throw new InvalidDataException("Heartbeat response request_id does not match.");

                    if (response.Payload.TryGetProperty("trading_enabled", out var trading) &&
                        trading.ValueKind == JsonValueKind.True)
                    {
                        throw new InvalidDataException("Task 002 Engine unexpectedly reported trading_enabled=true.");
                    }

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
            new { component = "desktop", desktop_version = "0.2.0-task002" });

        var response = await SendReceiveAsync(hello, TimeSpan.FromSeconds(3), cancellationToken);

        if (response.Type != "hello_ack")
            throw new InvalidDataException($"Unexpected hello response: {response.Type}");

        if (!string.Equals(response.RequestId, hello.RequestId, StringComparison.Ordinal))
            throw new InvalidDataException("hello_ack request_id does not match.");

        if (response.Payload.TryGetProperty("trading_enabled", out var trading) &&
            trading.ValueKind == JsonValueKind.True)
        {
            throw new InvalidDataException("Task 002 Engine unexpectedly reported trading_enabled=true.");
        }
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
            new EngineStateChangedEventArgs(state, detail, LastHeartbeatUtc));
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
