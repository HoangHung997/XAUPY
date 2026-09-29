using System.Globalization;
using System.Text.Json;
using Microsoft.VisualBasic.FileIO;
using XAUPY.Ipc;

namespace XAUPY.Desktop;

/// <summary>Read a user-selected archive without silently mixing symbols or frames.</summary>
internal static class ChartHistoryReader
{
    private const long MaxBytes = 256L * 1024 * 1024;
    private const int MaxBars = 2_000_000;
    private static readonly HashSet<string> Frames = ["M1", "M3", "M5", "M15", "M30", "H1", "H2", "H4", "D1"];

    internal static (string Symbol, string Timeframe, MarketBar[] Bars) Read(string path)
    {
        if (new FileInfo(path).Length > MaxBytes)
            throw new InvalidDataException("Chart archive exceeds 256 MiB; split the selected range.");
        var bars = new List<MarketBar>();
        string symbol = Path.GetFileNameWithoutExtension(path), frame = "M1";
        string? declaredSymbol = null, declaredFrame = null;
        void Identity(string? nextSymbol, string? nextFrame)
        {
            if (nextSymbol is not null)
            {
                nextSymbol = nextSymbol.Trim();
                if (nextSymbol.Length is 0 or > 128 || nextSymbol.Any(char.IsControl))
                    throw new InvalidDataException("Invalid chart symbol.");
                if (declaredSymbol is not null && declaredSymbol != nextSymbol)
                    throw new InvalidDataException("Chart archive contains mixed symbols.");
                declaredSymbol = symbol = nextSymbol;
            }
            if (nextFrame is not null)
            {
                nextFrame = nextFrame.Trim().ToUpperInvariant();
                if (!Frames.Contains(nextFrame)) throw new InvalidDataException("Unsupported chart timeframe.");
                if (declaredFrame is not null && declaredFrame != nextFrame)
                    throw new InvalidDataException("Chart archive contains mixed timeframes.");
                declaredFrame = frame = nextFrame;
            }
        }
        void Add(MarketBar b)
        {
            if (bars.Count >= MaxBars) throw new InvalidDataException("Chart archive exceeds two million bars.");
            if (b.Time <= 0 || b.Time >= 253402300799 || b.TickVolume < 0 ||
                !double.IsFinite(b.Open) || !double.IsFinite(b.High) || !double.IsFinite(b.Low) || !double.IsFinite(b.Close) ||
                b.Low > Math.Min(b.Open, b.Close) || b.High < Math.Max(b.Open, b.Close) ||
                (bars.Count > 0 && bars[^1].Time >= b.Time))
                throw new InvalidDataException("Bars must be finite, ordered, unique and have valid OHLC/volume values.");
            bars.Add(b);
        }
        if (Path.GetExtension(path).Equals(".json", StringComparison.OrdinalIgnoreCase))
        {
            using var stream = File.OpenRead(path);
            using var doc = JsonDocument.Parse(stream);
            var root = doc.RootElement;
            Identity(root.GetProperty("symbol").GetString(), root.TryGetProperty("timeframe", out var tf) ? tf.GetString() : "M1");
            foreach (var b in root.GetProperty("bars").EnumerateArray())
                Add(new MarketBar(b.GetProperty("time").GetInt64(), b.GetProperty("open").GetDouble(),
                    b.GetProperty("high").GetDouble(), b.GetProperty("low").GetDouble(), b.GetProperty("close").GetDouble(),
                    b.TryGetProperty("tick_volume", out var volume) ? volume.GetInt64() : 0));
        }
        else
        {
            // TextFieldParser handles quoted commas, escaped quotes and multiline fields.
            using var reader = new TextFieldParser(path, System.Text.Encoding.UTF8, true) {
                TextFieldType = FieldType.Delimited, HasFieldsEnclosedInQuotes = true, TrimWhiteSpace = true };
            reader.SetDelimiters(",");
            var header = reader.ReadFields() ?? throw new InvalidDataException("CSV header is missing.");
            header = header.Select(v => v.Trim().TrimStart('\uFEFF').ToLowerInvariant()).ToArray();
            if (header.Distinct().Count() != header.Length) throw new InvalidDataException("Duplicate CSV columns.");
            var columns = header.Select((name, i) => (name, i)).ToDictionary(v => v.name, v => v.i);
            foreach (string name in new[] { "time", "open", "high", "low", "close" })
                if (!columns.ContainsKey(name)) throw new InvalidDataException("Missing CSV column: " + name);
            while (!reader.EndOfData)
            {
                var row = reader.ReadFields();
                if (row is null) break;
                if (row.Length != header.Length) throw new InvalidDataException("CSV row has a different column count.");
                string Value(string name) => row[columns[name]];
                double Number(string name) => double.Parse(Value(name), NumberStyles.Float, CultureInfo.InvariantCulture);
                Identity(columns.ContainsKey("symbol") ? Value("symbol") : null, columns.ContainsKey("timeframe") ? Value("timeframe") : null);
                Add(new MarketBar(long.Parse(Value("time"), CultureInfo.InvariantCulture), Number("open"), Number("high"),
                    Number("low"), Number("close"), columns.ContainsKey("tick_volume") ? long.Parse(Value("tick_volume"), CultureInfo.InvariantCulture) : 0));
            }
            string directory = Path.GetDirectoryName(Path.GetFullPath(path))!;
            string manifest = Path.Combine(directory, "manifest.json");
            if (File.Exists(manifest))
            {
                if (new FileInfo(manifest).Length > 2 * 1024 * 1024) throw new InvalidDataException("Chart manifest exceeds 2 MiB.");
                using var doc = JsonDocument.Parse(File.ReadAllText(manifest));
                var comparison = OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
                if (doc.RootElement.TryGetProperty("timeframes", out var entries) && entries.ValueKind == JsonValueKind.Object)
                    foreach (var entry in entries.EnumerateObject())
                    {
                        if (!entry.Value.TryGetProperty("path", out var file) || file.ValueKind != JsonValueKind.String) continue;
                        var selected = file.GetString();
                        if (string.IsNullOrWhiteSpace(selected)) continue;
                        // Relative manifests are anchored to the manifest, never the process working directory.
                        string candidate = Path.GetFullPath(selected, directory);
                        if (string.Equals(candidate, Path.GetFullPath(path), comparison))
                            Identity(doc.RootElement.GetProperty("symbol").GetString(), entry.Name);
                    }
            }
        }
        if (bars.Count == 0) throw new InvalidDataException("No chart bars in the selected file.");
        Identity(symbol, frame);
        return (symbol, frame, bars.ToArray());
    }
}
