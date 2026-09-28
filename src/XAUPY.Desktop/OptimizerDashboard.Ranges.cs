using System.Globalization;
using System.Text.Json;
using Avalonia.Controls;
using Avalonia.Layout;
using Avalonia.Interactivity;

namespace XAUPY.Desktop;

public partial class OptimizerDashboard
{
    private sealed record ExtraRange(TextBox Min, TextBox Max, TextBox Step);
    private readonly Dictionary<string, ExtraRange> _extraRanges = new();
    private void ExtraRanges_OnClick(object? sender, RoutedEventArgs e)
    {
        var panel = this.FindControl<Border>("ExtraRangesPanel")!;
        panel.IsVisible = !panel.IsVisible;
    }

    private void InitializeExtraRanges(JsonElement profile)
    {
        _extraRanges.Clear();
        var host = this.FindControl<StackPanel>("ExtraRangesHost")!;
        host.Children.Clear();
        var fields = new[] {
            ("pullback", "rsi_period", "RSI nhịp hồi", "rsi_enabled", 1d),
            ("trigger", "rsi_period", "RSI xác nhận", "rsi_enabled", 1d),
            ("pullback", "z_period", "Z nhịp hồi", "z_enabled", 1d),
            ("trigger", "z_period", "Z xác nhận", "z_enabled", 1d),
            ("pullback", "z_buy_level", "Z mua ≤", "z_enabled", .1d),
            ("pullback", "z_sell_level", "Z bán ≥", "z_enabled", .1d),
            ("trigger", "z_reversal_delta", "Z hồi từ đỉnh/đáy", "z_enabled", .1d),
        };
        host.Children.Add(new TextBlock { Text = "Tham số                           Min           Max          Bước", FontSize = 12 });
        foreach (var (section, key, label, enabledKey, step) in fields)
        {
            string path = section + "." + key;
            if (path == _triggerDeltaPath) continue; // Already represented in the main table.
            bool enabled = GetBool(profile, section, enabledKey) == true;
            double value = GetDouble(profile, section, key) ?? 0;
            var min = new TextBox { Text = Format(value) };
            var max = new TextBox { Text = Format(value) };
            var delta = new TextBox { Text = Format(step) };
            var row = new Grid { ColumnDefinitions = new ColumnDefinitions("1.3*,1*,1*,.75*"), ColumnSpacing = 6, IsEnabled = enabled };
            row.Children.Add(new TextBlock { Text = label, VerticalAlignment = VerticalAlignment.Center });
            foreach (var (box, column) in new[] { (min, 1), (max, 2), (delta, 3) })
            {
                Grid.SetColumn(box, column); row.Children.Add(box); box.TextChanged += ParameterText_OnChanged;
            }
            host.Children.Add(row);
            if (enabled) _extraRanges[path] = new ExtraRange(min, max, delta);
        }
    }

    private IEnumerable<Dictionary<string, object>> ExtraParameterRanges()
    {
        foreach (var (path, range) in _extraRanges)
        {
            if (!TryNumber(range.Min.Text, out var min) || !TryNumber(range.Max.Text, out var max) ||
                !TryNumber(range.Step.Text, out var step) || step <= 0 || max < min)
                throw new InvalidDataException($"{path}: min/max/bước không hợp lệ.");
            if (path.EndsWith("_period", StringComparison.Ordinal) && (min % 1 != 0 || max % 1 != 0 || step % 1 != 0))
                throw new InvalidDataException($"{path}: chu kỳ và bước phải là số nguyên.");
            yield return new Dictionary<string, object> { ["path"] = path, ["min"] = min, ["max"] = max, ["step"] = step };
        }
    }
}
