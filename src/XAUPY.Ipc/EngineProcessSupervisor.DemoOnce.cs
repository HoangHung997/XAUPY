namespace XAUPY.Ipc;

public sealed partial class EngineProcessSupervisor
{
    public Task<DemoOnceResponse> GetDemoOnceStatusAsync(CancellationToken cancellationToken = default) =>
        SendDemoOnceAsync("demo_once_status", new { }, cancellationToken);

    public Task<DemoOnceResponse> ArmDemoOnceAsync(DemoOnceContext context, Guid attemptId, double maxVolume,
        int durationSeconds, bool confirmed, CancellationToken cancellationToken = default)
    {
        if (!confirmed || !context.CanArm || attemptId == Guid.Empty || !double.IsFinite(maxVolume) ||
            maxVolume <= 0 || maxVolume > .01 || durationSeconds is < 1 or > 86400)
            throw new InvalidOperationException("Cần xác nhận tài khoản DEMO, tối đa 0.01 lot và thời hạn 1–86400 giây.");
        return SendDemoOnceAsync("demo_once_arm", new
        {
            confirmed, attempt_id = attemptId.ToString(), account_login = context.AccountLogin,
            account_server = context.AccountServer, symbol = context.Symbol, magic = context.Magic,
            profile_hash = context.ProfileHash, max_volume = maxVolume, duration_seconds = durationSeconds
        }, cancellationToken);
    }

    public Task<DemoOnceResponse> CancelDemoOnceAsync(string attemptId, CancellationToken cancellationToken = default)
    {
        if (!Guid.TryParse(attemptId, out _)) throw new InvalidOperationException("Không có lần chờ hợp lệ để dừng.");
        return SendDemoOnceAsync("demo_once_cancel", new { attempt_id = attemptId }, cancellationToken);
    }

    private async Task<DemoOnceResponse> SendDemoOnceAsync(string kind, object payload, CancellationToken cancellationToken)
    {
        ThrowIfDisposed();
        if (State != EngineConnectionState.Ready) throw new InvalidOperationException("Chờ Engine kết nối trước khi điều khiển DEMO.");
        var response = await SendReceiveAsync(ProtocolEnvelope.Create(kind, payload), TimeSpan.FromSeconds(5), cancellationToken);
        if (response.Type != kind + "_ack") throw new InvalidDataException($"Unexpected demo-once response: {response.Type}");
        RejectUnexpectedExecutionEnable(response);
        var result = DemoOnceResponse.Parse(response.Payload);
        DemoOnce = result.Status;
        return result;
    }
}
