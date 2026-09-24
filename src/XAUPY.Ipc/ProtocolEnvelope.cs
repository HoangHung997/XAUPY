using System.Text.Json;
using System.Text.Json.Serialization;

namespace XAUPY.Ipc;

public sealed record ProtocolEnvelope
{
    public const int CurrentSchemaVersion = 1;

    private static readonly JsonSerializerOptions SerializerOptions = new()
    {
        PropertyNamingPolicy = null,
        WriteIndented = false
    };

    [JsonPropertyName("schema_version")]
    public int SchemaVersion { get; init; }

    [JsonPropertyName("type")]
    public string Type { get; init; } = string.Empty;

    [JsonPropertyName("request_id")]
    public string RequestId { get; init; } = string.Empty;

    [JsonPropertyName("sent_at_utc")]
    public string SentAtUtc { get; init; } = string.Empty;

    [JsonPropertyName("payload")]
    public JsonElement Payload { get; init; }

    public static ProtocolEnvelope Create(string type, object? payload = null, string? requestId = null)
    {
        if (string.IsNullOrWhiteSpace(type))
            throw new ArgumentException("Message type is required.", nameof(type));

        return new ProtocolEnvelope
        {
            SchemaVersion = CurrentSchemaVersion,
            Type = type,
            RequestId = requestId ?? Guid.NewGuid().ToString(),
            SentAtUtc = DateTimeOffset.UtcNow.ToString("O"),
            Payload = JsonSerializer.SerializeToElement(payload ?? new { }, SerializerOptions)
        };
    }

    public static ProtocolEnvelope CreateResponse(string type, string requestId, object? payload = null) =>
        Create(type, payload, requestId);

    public string ToJson() => JsonSerializer.Serialize(this, SerializerOptions);

    public static ProtocolEnvelope Parse(string json)
    {
        if (string.IsNullOrWhiteSpace(json))
            throw new InvalidDataException("IPC payload is empty.");

        var envelope = JsonSerializer.Deserialize<ProtocolEnvelope>(json, SerializerOptions)
            ?? throw new InvalidDataException("IPC payload could not be decoded.");

        envelope.Validate();
        return envelope;
    }

    public void Validate()
    {
        if (SchemaVersion != CurrentSchemaVersion)
            throw new InvalidDataException(
                $"Unsupported IPC schema version {SchemaVersion}; expected {CurrentSchemaVersion}.");

        if (string.IsNullOrWhiteSpace(Type))
            throw new InvalidDataException("IPC message type is required.");

        if (!Guid.TryParse(RequestId, out _))
            throw new InvalidDataException("IPC request_id must be a UUID.");

        if (!DateTimeOffset.TryParse(SentAtUtc, out _))
            throw new InvalidDataException("IPC sent_at_utc must be an ISO-8601 timestamp.");

        if (Payload.ValueKind != JsonValueKind.Object)
            throw new InvalidDataException("IPC payload must be a JSON object.");
    }
}
