using System.Text.Json;

namespace XAUPY.Ipc;

public sealed record JournalEventSnapshot(
    long Sequence,
    string EventId,
    string TimestampUtc,
    string Level,
    string Source,
    string Tag,
    string Message,
    JsonElement Details,
    string? CorrelationId,
    string? Symbol,
    string? ProfileHash,
    bool Bookmarked)
{
    public static bool TryParse(JsonElement item, out JournalEventSnapshot value)
    {
        value = default!;
        if (item.ValueKind != JsonValueKind.Object)
            return false;

        var sequence = OverviewSnapshot.ReadLong(item, "sequence");
        var eventId = OverviewSnapshot.ReadString(item, "event_id");
        var timestamp = OverviewSnapshot.ReadString(item, "timestamp_utc");
        var level = OverviewSnapshot.ReadString(item, "level");
        var source = OverviewSnapshot.ReadString(item, "source");
        var tag = OverviewSnapshot.ReadString(item, "tag");
        var message = OverviewSnapshot.ReadString(item, "message");

        if (sequence is null ||
            string.IsNullOrWhiteSpace(eventId) ||
            string.IsNullOrWhiteSpace(timestamp) ||
            string.IsNullOrWhiteSpace(level) ||
            string.IsNullOrWhiteSpace(source) ||
            string.IsNullOrWhiteSpace(tag) ||
            string.IsNullOrWhiteSpace(message))
        {
            return false;
        }

        JsonElement details = JsonSerializer.SerializeToElement(new { });
        if (item.TryGetProperty("details", out var detailsElement) &&
            detailsElement.ValueKind == JsonValueKind.Object)
        {
            details = detailsElement.Clone();
        }

        value = new JournalEventSnapshot(
            sequence.Value,
            eventId!,
            timestamp!,
            level!,
            source!,
            tag!,
            message!,
            details,
            OverviewSnapshot.ReadString(item, "correlation_id"),
            OverviewSnapshot.ReadString(item, "symbol"),
            OverviewSnapshot.ReadString(item, "profile_hash"),
            OverviewSnapshot.ReadBool(item, "bookmarked"));
        return true;
    }
}

public sealed record JournalSummarySnapshot(
    int SchemaVersion,
    string DateScope,
    int Total,
    IReadOnlyDictionary<string, int> LevelCounts,
    IReadOnlyDictionary<string, int> SourceCounts,
    long LatestSequence,
    IReadOnlyList<JournalEventSnapshot> RecentAlerts,
    IReadOnlyList<JournalEventSnapshot> Bookmarks,
    int InvalidReplayLines,
    int DuplicateReplayLines)
{
    public static JournalSummarySnapshot Empty { get; } = new(
        1,
        "TODAY",
        0,
        EmptyLevelCounts(),
        EmptySourceCounts(),
        0,
        Array.Empty<JournalEventSnapshot>(),
        Array.Empty<JournalEventSnapshot>(),
        0,
        0);

    public static JournalSummarySnapshot FromHeartbeatPayload(JsonElement heartbeatPayload)
    {
        if (!heartbeatPayload.TryGetProperty("journal_summary", out var summary) ||
            summary.ValueKind != JsonValueKind.Object)
        {
            return Empty;
        }

        return FromElement(summary);
    }

    internal static JournalSummarySnapshot FromElement(JsonElement summary)
    {
        var levels = ReadCounts(summary, "level_counts", EmptyLevelCounts());
        var sources = ReadCounts(summary, "source_counts", EmptySourceCounts());

        return new JournalSummarySnapshot(
            OverviewSnapshot.ReadInt(summary, "schema_version") ?? 1,
            OverviewSnapshot.ReadString(summary, "date_scope") ?? "TODAY",
            OverviewSnapshot.ReadInt(summary, "total") ?? 0,
            levels,
            sources,
            OverviewSnapshot.ReadLong(summary, "latest_sequence") ?? 0,
            ReadEvents(summary, "recent_alerts"),
            ReadEvents(summary, "bookmarks"),
            OverviewSnapshot.ReadInt(summary, "invalid_replay_lines") ?? 0,
            OverviewSnapshot.ReadInt(summary, "duplicate_replay_lines") ?? 0);
    }

    private static IReadOnlyDictionary<string, int> ReadCounts(
        JsonElement parent,
        string name,
        IReadOnlyDictionary<string, int> fallback)
    {
        if (!parent.TryGetProperty(name, out var element) ||
            element.ValueKind != JsonValueKind.Object)
        {
            return fallback;
        }

        var result = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
        foreach (var property in element.EnumerateObject())
        {
            if (property.Value.ValueKind == JsonValueKind.Number &&
                property.Value.TryGetInt32(out var value))
            {
                result[property.Name] = value;
            }
        }
        return result;
    }

    internal static IReadOnlyList<JournalEventSnapshot> ReadEvents(
        JsonElement parent,
        string name)
    {
        if (!parent.TryGetProperty(name, out var element) ||
            element.ValueKind != JsonValueKind.Array)
        {
            return Array.Empty<JournalEventSnapshot>();
        }

        var result = new List<JournalEventSnapshot>();
        foreach (var item in element.EnumerateArray())
        {
            if (JournalEventSnapshot.TryParse(item, out var value))
                result.Add(value);
        }
        return result;
    }

    private static IReadOnlyDictionary<string, int> EmptyLevelCounts() =>
        new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase)
        {
            ["INFO"] = 0,
            ["WARN"] = 0,
            ["ERROR"] = 0,
            ["DEBUG"] = 0,
        };

    private static IReadOnlyDictionary<string, int> EmptySourceCounts() =>
        new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase)
        {
            ["System"] = 0,
            ["MT5"] = 0,
            ["EA Bridge"] = 0,
            ["Python Engine"] = 0,
            ["Strategy"] = 0,
            ["Orders"] = 0,
            ["Alerts"] = 0,
        };
}

public sealed record JournalQueryResult(
    bool Ok,
    string DateScope,
    int TotalMatched,
    IReadOnlyList<JournalEventSnapshot> Events,
    long LatestSequence,
    int InvalidReplayLines,
    JournalSummarySnapshot Summary,
    IReadOnlyList<string> Errors)
{
    public static JournalQueryResult FromAck(JsonElement payload)
    {
        bool ok = OverviewSnapshot.ReadBool(payload, "ok");
        var errors = ReadErrors(payload);

        if (!ok ||
            !payload.TryGetProperty("journal", out var journal) ||
            journal.ValueKind != JsonValueKind.Object)
        {
            return new JournalQueryResult(
                false,
                "TODAY",
                0,
                Array.Empty<JournalEventSnapshot>(),
                0,
                0,
                JournalSummarySnapshot.Empty,
                errors);
        }

        var summary = payload.TryGetProperty("summary", out var summaryElement) &&
                      summaryElement.ValueKind == JsonValueKind.Object
            ? JournalSummarySnapshot.FromElement(summaryElement)
            : JournalSummarySnapshot.Empty;

        return new JournalQueryResult(
            true,
            OverviewSnapshot.ReadString(journal, "date_scope") ?? "TODAY",
            OverviewSnapshot.ReadInt(journal, "total_matched") ?? 0,
            JournalSummarySnapshot.ReadEvents(journal, "events"),
            OverviewSnapshot.ReadLong(journal, "latest_sequence") ?? 0,
            OverviewSnapshot.ReadInt(journal, "invalid_replay_lines") ?? 0,
            summary,
            errors);
    }

    internal static IReadOnlyList<string> ReadErrors(JsonElement payload)
    {
        if (!payload.TryGetProperty("errors", out var errorsElement) ||
            errorsElement.ValueKind != JsonValueKind.Array)
        {
            return Array.Empty<string>();
        }

        return errorsElement
            .EnumerateArray()
            .Where(item => item.ValueKind == JsonValueKind.String)
            .Select(item => item.GetString() ?? string.Empty)
            .Where(item => !string.IsNullOrWhiteSpace(item))
            .ToArray();
    }
}

public sealed record JournalBookmarkResult(
    bool Ok,
    JournalEventSnapshot? Event,
    JournalSummarySnapshot Summary,
    IReadOnlyList<string> Errors)
{
    public static JournalBookmarkResult FromAck(JsonElement payload)
    {
        bool ok = OverviewSnapshot.ReadBool(payload, "ok");
        JournalEventSnapshot? journalEvent = null;

        if (ok &&
            payload.TryGetProperty("event", out var eventElement) &&
            JournalEventSnapshot.TryParse(eventElement, out var parsed))
        {
            journalEvent = parsed;
        }

        var summary = payload.TryGetProperty("summary", out var summaryElement) &&
                      summaryElement.ValueKind == JsonValueKind.Object
            ? JournalSummarySnapshot.FromElement(summaryElement)
            : JournalSummarySnapshot.Empty;

        return new JournalBookmarkResult(
            ok,
            journalEvent,
            summary,
            JournalQueryResult.ReadErrors(payload));
    }
}
