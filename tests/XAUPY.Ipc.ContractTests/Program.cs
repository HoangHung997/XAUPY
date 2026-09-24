using System.Text.Json;
using XAUPY.Ipc;

var passed = 0;

void Check(bool condition, string name)
{
    if (!condition)
        throw new Exception($"FAILED: {name}");

    passed++;
    Console.WriteLine($"PASS: {name}");
}

var hello = ProtocolEnvelope.Create("hello", new { component = "contract-test" });
var parsed = ProtocolEnvelope.Parse(hello.ToJson());

Check(parsed.Type == "hello", "round-trip message type");
Check(parsed.RequestId == hello.RequestId, "round-trip request_id");
Check(parsed.SchemaVersion == ProtocolEnvelope.CurrentSchemaVersion, "schema version");

var ack = ProtocolEnvelope.CreateResponse(
    "hello_ack",
    hello.RequestId,
    new { trading_enabled = false });

Check(ack.RequestId == hello.RequestId, "response correlation");
Check(!ack.Payload.GetProperty("trading_enabled").GetBoolean(), "trading disabled");

var another = ProtocolEnvelope.Create("heartbeat");
Check(another.RequestId != hello.RequestId, "request IDs are unique");

var raw = JsonSerializer.Deserialize<Dictionary<string, object?>>(hello.ToJson())!;
raw["schema_version"] = 999;
var invalidSchema = JsonSerializer.Serialize(raw);

var schemaRejected = false;
try
{
    ProtocolEnvelope.Parse(invalidSchema);
}
catch (InvalidDataException)
{
    schemaRejected = true;
}

Check(schemaRejected, "unsupported schema rejected");

Console.WriteLine($"XAUPY IPC contract self-test complete: {passed} checks passed.");
