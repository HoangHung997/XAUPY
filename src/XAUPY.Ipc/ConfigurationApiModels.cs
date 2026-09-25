using System.Text.Json;

namespace XAUPY.Ipc;

public sealed record ConfigValidationResult(
    bool Valid,
    IReadOnlyList<string> Errors,
    JsonElement? Profile);

public sealed record ConfigApplyResult(
    bool Applied,
    IReadOnlyList<string> Errors,
    JsonElement? Profile);

public static class ConfigurationApiParser
{
    public static ConfigValidationResult ParseValidation(JsonElement payload)
    {
        bool valid = payload.TryGetProperty("valid", out var validElement) &&
                     validElement.ValueKind == JsonValueKind.True;

        var errors = ReadErrors(payload);
        JsonElement? profile = null;

        if (valid &&
            payload.TryGetProperty("profile", out var profileElement) &&
            profileElement.ValueKind == JsonValueKind.Object)
        {
            profile = profileElement.Clone();
        }

        return new ConfigValidationResult(valid, errors, profile);
    }

    public static ConfigApplyResult ParseApply(JsonElement payload)
    {
        bool applied = payload.TryGetProperty("applied", out var appliedElement) &&
                       appliedElement.ValueKind == JsonValueKind.True;

        var errors = ReadErrors(payload);
        JsonElement? profile = null;

        if (applied &&
            payload.TryGetProperty("profile", out var profileElement) &&
            profileElement.ValueKind == JsonValueKind.Object)
        {
            profile = profileElement.Clone();
        }

        return new ConfigApplyResult(applied, errors, profile);
    }

    private static IReadOnlyList<string> ReadErrors(JsonElement payload)
    {
        var result = new List<string>();

        if (!payload.TryGetProperty("errors", out var errorsElement) ||
            errorsElement.ValueKind != JsonValueKind.Array)
        {
            return result;
        }

        foreach (var item in errorsElement.EnumerateArray())
        {
            if (item.ValueKind == JsonValueKind.String && item.GetString() is { } value)
                result.Add(value);
        }

        return result;
    }
}
