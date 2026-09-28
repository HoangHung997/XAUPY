using System.Text.Json;

namespace XAUPY.Ipc;

public sealed partial class EngineProcessSupervisor
{
    public Task<JsonElement> SetExecutionModeAsync(string mode, bool confirmed, CancellationToken cancellationToken = default) =>
        ExecutionRequestAsync("execution_mode_set", new { mode, confirmed, account_login = OrdersPositions.AccountLogin,
            account_server = OrdersPositions.AccountServer, symbol = OrdersPositions.Symbol, magic = OrdersPositions.Magic }, cancellationToken);

    public async Task<JsonElement> ExecutionRequestAsync(string type, object payload, CancellationToken cancellationToken = default)
    {
        var response = await SendReceiveAsync(ProtocolEnvelope.Create(type, payload), TimeSpan.FromSeconds(5), cancellationToken);
        if (response.Type != type + "_ack") throw new InvalidDataException($"Phản hồi không hợp lệ: {response.Type}");
        RejectUnexpectedExecutionEnable(response);
        return response.Payload.Clone();
    }

    public async Task<ManualActionResult> ExecuteManualActionAsync(string action, bool confirmed, long? ticket = null,
        double? volume = null, double? slPoints = null, double? tpPoints = null, double? percent = null,
        double? price = null, double? sl = null, double? tp = null, string? side = null, string? orderType = null,
        string? intentId = null, CancellationToken cancellationToken = default)
    {
        string id = intentId ?? Guid.NewGuid().ToString();
        var payload = new { intent_id = id, action, confirmed, ticket, volume, sl_points = slPoints, tp_points = tpPoints,
            percent, price, sl, tp, side, order_type = orderType };
        var queued = await ExecutionRequestAsync("execution_action", payload, cancellationToken);
        var result = ManualActionResult.FromAck(queued);
        if (!result.Accepted) return result;
        // Query the original ID only. A timeout never resubmits an order.
        for (int i = 0; i < 20; i++)
        {
            await Task.Delay(350, cancellationToken);
            var report = await ExecutionRequestAsync("execution_history", new { limit = 100 }, cancellationToken);
            if (!report.TryGetProperty("items", out var items)) continue;
            foreach (var item in items.EnumerateArray())
            {
                if (OverviewSnapshot.ReadString(item, "id") != id) continue;
                string state = OverviewSnapshot.ReadString(item, "state") ?? "UNKNOWN";
                if (state is "QUEUED" or "DISPATCHED" or "BATCH_QUEUED") break;
                string reason = item.TryGetProperty("result", out var evidence) && evidence.ValueKind == JsonValueKind.Object
                    ? OverviewSnapshot.ReadString(evidence, "reason") ?? state : state;
                return result with { Code = state, Message = reason, Accepted = state is "CONFIRMED" or "APPLIED_LOCAL", BrokerMutated = state == "CONFIRMED" };
            }
        }
        return result with { Code = "AWAITING_BROKER", Message = "Đang đối chiếu broker. Xem tiến trình lệnh; không gửi lại thao tác.", BrokerMutated = false };
    }
}
