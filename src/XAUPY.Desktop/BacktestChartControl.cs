using Avalonia;
using Avalonia.Controls;
using Avalonia.Media;
using XAUPY.Ipc;

namespace XAUPY.Desktop;

public sealed class BacktestChartControl : Control
{
    private IReadOnlyList<BacktestEquityPoint> _equity = Array.Empty<BacktestEquityPoint>();
    private IReadOnlyList<BacktestDrawdownPoint> _drawdown = Array.Empty<BacktestDrawdownPoint>();
    private bool _drawdownMode;

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

        var bounds = Bounds;
        if (bounds.Width <= 4 || bounds.Height <= 4)
            return;

        var background = new SolidColorBrush(Color.Parse("#041526"));
        var gridBrush = new SolidColorBrush(Color.Parse("#173B57"));
        var axisBrush = new SolidColorBrush(Color.Parse("#315B78"));
        var equityBrush = new SolidColorBrush(Color.Parse("#1B8FFF"));
        var balanceBrush = new SolidColorBrush(Color.Parse("#30D08A"));
        var drawdownBrush = new SolidColorBrush(Color.Parse("#FF3C55"));

        context.DrawRectangle(background, null, new Rect(0, 0, bounds.Width, bounds.Height));

        var gridPen = new Pen(gridBrush, 1);
        for (int i = 1; i < 5; i++)
        {
            double y = bounds.Height * i / 5.0;
            context.DrawLine(gridPen, new Point(0, y), new Point(bounds.Width, y));
        }
        for (int i = 1; i < 7; i++)
        {
            double x = bounds.Width * i / 7.0;
            context.DrawLine(gridPen, new Point(x, 0), new Point(x, bounds.Height));
        }

        context.DrawLine(
            new Pen(axisBrush, 1),
            new Point(0, bounds.Height - 1),
            new Point(bounds.Width, bounds.Height - 1));

        if (_drawdownMode)
            DrawDrawdown(context, bounds, drawdownBrush);
        else
            DrawEquity(context, bounds, equityBrush, balanceBrush);
    }

    private void DrawEquity(
        DrawingContext context,
        Rect bounds,
        IBrush equityBrush,
        IBrush balanceBrush)
    {
        if (_equity.Count < 2)
            return;

        var sampled = Sample(_equity, Math.Max(2, (int)Math.Min(bounds.Width, 420)));
        double min = sampled.Min(item => Math.Min(item.Balance, item.Equity));
        double max = sampled.Max(item => Math.Max(item.Balance, item.Equity));
        if (Math.Abs(max - min) < 1e-9)
        {
            max += 1;
            min -= 1;
        }

        DrawSeries(
            context,
            bounds,
            sampled.Select(item => item.Equity).ToArray(),
            min,
            max,
            new Pen(equityBrush, 2.2));

        DrawSeries(
            context,
            bounds,
            sampled.Select(item => item.Balance).ToArray(),
            min,
            max,
            new Pen(balanceBrush, 1.5));
    }

    private void DrawDrawdown(
        DrawingContext context,
        Rect bounds,
        IBrush drawdownBrush)
    {
        if (_drawdown.Count < 2)
            return;

        var sampled = Sample(_drawdown, Math.Max(2, (int)Math.Min(bounds.Width, 420)));
        double max = Math.Max(
            0.000001,
            sampled.Max(item => item.DrawdownPct));

        var values = sampled.Select(item => -item.DrawdownPct).ToArray();
        DrawSeries(
            context,
            bounds,
            values,
            -max,
            0,
            new Pen(drawdownBrush, 2.0));
    }

    private static void DrawSeries(
        DrawingContext context,
        Rect bounds,
        IReadOnlyList<double> values,
        double min,
        double max,
        Pen pen)
    {
        if (values.Count < 2)
            return;

        double width = Math.Max(1, bounds.Width - 2);
        double height = Math.Max(1, bounds.Height - 2);
        double span = Math.Max(1e-12, max - min);

        for (int i = 1; i < values.Count; i++)
        {
            double x1 = 1 + width * (i - 1) / (values.Count - 1.0);
            double x2 = 1 + width * i / (values.Count - 1.0);
            double y1 = 1 + height * (1.0 - ((values[i - 1] - min) / span));
            double y2 = 1 + height * (1.0 - ((values[i] - min) / span));
            context.DrawLine(pen, new Point(x1, y1), new Point(x2, y2));
        }
    }

    private static IReadOnlyList<T> Sample<T>(
        IReadOnlyList<T> values,
        int maxPoints)
    {
        if (values.Count <= maxPoints)
            return values;

        var result = new List<T>(maxPoints);
        int lastIndex = -1;
        for (int step = 0; step < maxPoints; step++)
        {
            int index = (int)Math.Round(
                step * (values.Count - 1.0) / (maxPoints - 1.0));
            if (index == lastIndex)
                continue;
            result.Add(values[index]);
            lastIndex = index;
        }
        return result;
    }
}
