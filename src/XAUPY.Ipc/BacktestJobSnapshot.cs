using System.Text.Json;

namespace XAUPY.Ipc;

public sealed record BacktestJobSnapshot(string JobId, string State, int CompletedBars, int TotalBars, string? RunId)
{
    public static BacktestJobSnapshot FromAck(JsonElement payload)
    {
        if (!payload.TryGetProperty("ok", out var ok) || ok.ValueKind != JsonValueKind.True)
            throw new InvalidDataException(payload.TryGetProperty("errors", out var errors) ? errors.ToString() : "Backtest job rejected");
        var job = payload.GetProperty("job");
        var state = job.GetProperty("state").GetString()!;
        if (state == "FAILED") throw new InvalidDataException(job.GetProperty("errors").ToString());
        if (state is not ("QUEUED" or "RUNNING" or "CANCELLING" or "CANCELLED" or "COMPLETED"))
            throw new InvalidDataException("Unknown backtest job state");
        var id = job.GetProperty("job_id").GetString()!;
        if (!Guid.TryParse(id, out _)) throw new InvalidDataException("Invalid backtest job id");
        return new(id, state, job.GetProperty("completed_bars").GetInt32(), job.GetProperty("total_bars").GetInt32(),
            job.TryGetProperty("run_id", out var run) && run.ValueKind == JsonValueKind.String ? run.GetString() : null);
    }
}
