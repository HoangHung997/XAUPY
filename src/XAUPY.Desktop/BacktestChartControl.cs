using System.Globalization;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Media;
using Avalonia.VisualTree;
using XAUPY.Ipc;

namespace XAUPY.Desktop;

/// <summary>Equity and drawdown axes use only the received backtest result.</summary>
public sealed class BacktestChartControl : Control
{
    private IReadOnlyList<BacktestEquityPoint> _equity = Array.Empty<BacktestEquityPoint>();
    private IReadOnlyList<BacktestDrawdownPoint> _drawdown = Array.Empty<BacktestDrawdownPoint>();
    private bool _drawdownMode;
    private bool _toolbarAttached;
    private string _seriesMode = "Equity";
    private readonly List<(Border Chip, string Mode)> _chips = new();
    public string SeriesMode => _seriesMode;
    public string DrawdownUnit { get; private set; } = "PERCENT";
    public void SelectDrawdownUnit(string unit)
    {
        if(unit is not ("PERCENT" or "MONEY"))return;
        DrawdownUnit=unit;InvalidateVisual();
    }
    private double DrawdownValue(BacktestDrawdownPoint point) => DrawdownUnit=="MONEY" ? point.DrawdownUsd : point.DrawdownPct;
    public int TimezoneOffsetMinutes { get; set; }
    private static readonly IBrush EquityBrush = Brush("#1B8FFF");
    private static readonly IBrush BalanceBrush = Brush("#30D08A");
    private static readonly IBrush DrawdownBrush = Brush("#FF3C55");
    private static readonly IBrush LabelBrush = Brush("#C3D8EC");

    public void SelectSeries(string mode)
    {
        if (mode is not ("Balance" or "Equity" or "Cả hai")) return;
        _seriesMode = mode;
        foreach (var (chip, name) in _chips) chip.Background = Brush(name == mode ? "#0866F4" : "#081E34");
        InvalidateVisual();
    }

    protected override void OnAttachedToVisualTree(VisualTreeAttachmentEventArgs e)
    {
        base.OnAttachedToVisualTree(e);
        if (_toolbarAttached) return;
        var panel = this.GetVisualAncestors().OfType<Border>().FirstOrDefault(b => b.Classes.Contains("panel"));
        if (panel is null) return;
        _toolbarAttached = true;
        foreach (var chip in panel.GetVisualDescendants().OfType<Border>())
        {
            if (chip.Child is not TextBlock { Text: "Balance" or "Equity" or "Cả hai" } label) continue;
            var mode = label.Text!;
            _chips.Add((chip, mode));
            chip.Focusable = true;
            chip.Cursor = new Cursor(StandardCursorType.Hand);
            chip.PointerPressed += (_, args) => { if (!args.GetCurrentPoint(chip).Properties.IsLeftButtonPressed) return; SelectSeries(mode); args.Handled = true; };
            chip.KeyDown += (_, args) => { if (args.Key is not (Key.Enter or Key.Space)) return; SelectSeries(mode); args.Handled = true; };
        }
        SelectSeries(_seriesMode);
    }

    public void SetEquityData(IReadOnlyList<BacktestEquityPoint> points)
    {
        _drawdownMode = false;
        _equity = points;
        _drawdown = Array.Empty<BacktestDrawdownPoint>();
        InvalidateVisual();
    }

    public void SetDrawdownData(IReadOnlyList<BacktestDrawdownPoint> points)
    {
        _drawdownMode = true;
        _drawdown = points;
        _equity = Array.Empty<BacktestEquityPoint>();
        InvalidateVisual();
    }

    public void Clear()
    {
        _equity = Array.Empty<BacktestEquityPoint>();
        _drawdown = Array.Empty<BacktestDrawdownPoint>();
        InvalidateVisual();
    }

    public override void Render(DrawingContext context)
    {
        base.Render(context);
        if (Bounds.Width < 100 || Bounds.Height < 50) return;
        context.DrawRectangle(Brush("#041526"), null, new Rect(Bounds.Size));
        var plot = new Rect(56, 30, Bounds.Width - 66, Bounds.Height - 53);
        bool hasData = _drawdownMode ? _drawdown.Count >= 2 : _equity.Count >= 2;
        double min = 0, max = 1;
        long firstTime = 0, lastTime = 0;
        if (hasData && _drawdownMode)
        {
            max = 0;
            min = -Math.Max(0.01, _drawdown.Max(DrawdownValue) * 1.15);
            firstTime = _drawdown[0].Time;
            lastTime = _drawdown[^1].Time;
        }
        else if (hasData)
        {
            min = _equity.Min(x => Math.Min(x.Balance, x.Equity));
            max = _equity.Max(x => Math.Max(x.Balance, x.Equity));
            var pad = Math.Max(1, (max - min) * 0.08);
            min -= pad; max += pad;
            firstTime = _equity[0].Time;
            lastTime = _equity[^1].Time;
        }
        var gridPen = new Pen(Brush("#173B57"), 1, new DashStyle([3, 3], 0));
        for (int i = 0; i <= 5; i++)
        {
            double y = plot.Top + plot.Height * i / 5;
            context.DrawLine(gridPen, new Point(plot.Left, y), new Point(plot.Right, y));
            if (hasData)
            {
                var value = max - (max - min) * i / 5;
                var label = _drawdownMode ? value.ToString(Math.Abs(min) < 1 ? "0.000" : "0.0", CultureInfo.InvariantCulture) + (DrawdownUnit=="PERCENT" ? "%" : "") : value.ToString("N0", CultureInfo.InvariantCulture);
                var text = Text(label, LabelBrush, 11);
                context.DrawText(text, new Point(plot.Left - text.Width - 8, y - text.Height / 2));
            }
        }
        for (int i = 0; i <= 5; i++)
        {
            double x = plot.Left + plot.Width * i / 5;
            context.DrawLine(gridPen, new Point(x, plot.Top), new Point(x, plot.Bottom));
            if (hasData)
            {
                var epoch = firstTime + (long)((lastTime - firstTime) * (i / 5.0));
                string label;
                try { label = DateTimeOffset.FromUnixTimeSeconds(epoch).AddMinutes(TimezoneOffsetMinutes).ToString(lastTime-firstTime >= 60*86400L ? "MM/yyyy" : lastTime-firstTime < 86400 ? "HH:mm" : "dd/MM", CultureInfo.InvariantCulture); }
                catch (ArgumentOutOfRangeException) { label = "—"; }
                var text = Text(label, LabelBrush, 11);
                context.DrawText(text, new Point(Math.Clamp(x-text.Width/2, 0, Bounds.Width-text.Width), plot.Bottom+5));
            }
        }
        context.DrawLine(new Pen(Brush("#86AEC8")), plot.BottomLeft, plot.BottomRight);
        if (!hasData) return;
        double X(long time) => plot.Left + plot.Width * (time - firstTime) / Math.Max(1.0, lastTime-firstTime);
        double Y(double value) => plot.Bottom - plot.Height * (value-min) / (max-min);
        using (context.PushClip(plot))
        {
            if (_drawdownMode)
            {
                var points = _drawdown.Select(p => new Point(X(p.Time), Y(-DrawdownValue(p)))).ToArray();
                DrawSeries(context, points, DrawdownBrush, plot.Top, "#50FF3658");
            }
            else
            {
                if (_seriesMode is "Equity" or "Cả hai")
                    DrawSeries(context, _equity.Select(p => new Point(X(p.Time), Y(p.Equity))).ToArray(), EquityBrush, plot.Bottom, "#301A9FE6");
                if (_seriesMode is "Balance" or "Cả hai")
                    DrawSeries(context, _equity.Select(p => new Point(X(p.Time), Y(p.Balance))).ToArray(), BalanceBrush, plot.Bottom, _seriesMode == "Balance" ? "#3024D08A" : null);
            }
        }
        double highlight;
        double px;
        if (_drawdownMode) { var point = _drawdown.MaxBy(DrawdownValue)!; highlight = -DrawdownValue(point); px = X(point.Time); }
        else { var point = _equity[^1]; highlight = _seriesMode == "Balance" ? point.Balance : point.Equity; px = X(point.Time); }
        var py = Y(highlight);
        var color = _drawdownMode ? DrawdownBrush : _seriesMode == "Balance" ? BalanceBrush : EquityBrush;
        var valueText = Text(highlight.ToString(_drawdownMode && DrawdownUnit=="PERCENT" ? "0.00'%'" : "N2", CultureInfo.InvariantCulture), Brushes.White, 11);
        double pillWidth = valueText.Width + 12;
        double left = Math.Clamp(px-pillWidth/2, plot.Left, plot.Right-pillWidth);
        double top = Math.Clamp(py-27, plot.Top, plot.Bottom-23);
        context.DrawRectangle(color, null, new Rect(left, top, pillWidth, 21), 3, 3);
        context.DrawText(valueText, new Point(left+6, top+3));
        context.DrawEllipse(color, new Pen(Brushes.White, 1.5), new Point(px,py), 4,4);
    }

    private static void DrawSeries(DrawingContext context, IReadOnlyList<Point> points, IBrush stroke, double baseline, string? fill)
    {
        if (points.Count < 2) return;
        if (fill is not null)
        {
            var area = new StreamGeometry();
            using (var g = area.Open()) { g.BeginFigure(new Point(points[0].X, baseline), true); foreach (var point in points) g.LineTo(point); g.LineTo(new Point(points[^1].X, baseline)); g.EndFigure(true); }
            context.DrawGeometry(Brush(fill), null, area);
        }
        var line = new StreamGeometry();
        using (var g = line.Open()) { g.BeginFigure(points[0], false); foreach (var point in points.Skip(1)) g.LineTo(point); g.EndFigure(false); }
        context.DrawGeometry(null, new Pen(stroke, 1.7), line);
    }
    private static IBrush Brush(string color) => new SolidColorBrush(Color.Parse(color));
    private static FormattedText Text(string value, IBrush brush, double size) => new(value, CultureInfo.InvariantCulture, FlowDirection.LeftToRight, new Typeface("Segoe UI"), AppearanceService.Scale(size), brush);
}
