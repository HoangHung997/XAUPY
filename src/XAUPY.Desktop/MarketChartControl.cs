using System.Globalization;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Media;
using Avalonia.VisualTree;
using XAUPY.Ipc;

namespace XAUPY.Desktop;

/// <summary>A price chart of closed bars actually received from the MT5 bridge.</summary>
public sealed class MarketChartControl : Control
{
    private readonly Dictionary<string, SortedDictionary<long, MarketBar>> _history = new(StringComparer.OrdinalIgnoreCase);
    private string? _symbol;
    private string _timeframe = "M5";
    private double? _bid;
    private bool _connected;
    private bool _toolbarAttached;
    private bool _userSelectedTimeframe;
    private bool _showIndicators = true;
    private bool _lineMode;
    private string? _comparisonTimeframe;
    private TextBlock? _timeframeTitle;
    private readonly List<(Border Chip, string Timeframe)> _timeframeChips = new();
    private readonly Dictionary<Border, IBrush?> _chipBackgrounds = new();
    private static readonly string[] Timeframes = ["M1", "M3", "M5", "M15", "M30", "H1", "H2", "H4"];

    public string SelectedTimeframe => _timeframe;
    public string? ComparisonTimeframe => _comparisonTimeframe;
    public bool ShowIndicators => _showIndicators;

    public void SelectTimeframe(string timeframe)
    {
        if (!Timeframes.Contains(timeframe, StringComparer.OrdinalIgnoreCase)) return;
        _timeframe = timeframe.ToUpperInvariant();
        _userSelectedTimeframe = true;
        if (_comparisonTimeframe == _timeframe) _comparisonTimeframe = null;
        UpdateToolbar();
        InvalidateVisual();
    }

    public void SetComparisonTimeframe(string? timeframe)
    {
        if (timeframe is not null && !Timeframes.Contains(timeframe, StringComparer.OrdinalIgnoreCase)) return;
        _comparisonTimeframe = string.Equals(timeframe, _timeframe, StringComparison.OrdinalIgnoreCase) ? null : timeframe?.ToUpperInvariant();
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
            if (chip.Child is not TextBlock { Text: { } tf } || !Timeframes.Contains(tf)) continue;
            _timeframeChips.Add((chip, tf));
            _chipBackgrounds[chip] = chip.Classes.Contains("panelSoft") ? chip.Background : Brush("#081E34");
            Activate(chip, () => SelectTimeframe(tf));
        }
        foreach (var label in panel.GetVisualDescendants().OfType<TextBlock>())
        {
            if (label.GetVisualParent() is StackPanel && Timeframes.Contains(label.Text)) _timeframeTitle = label;
            if (label.Text?.Contains("So sánh", StringComparison.Ordinal) == true)
            {
                ToolTip.SetTip(label, "So sánh biến động cùng symbol ở khung khác; đường so sánh chuẩn hóa về giá đầu khoảng hiển thị.");
                Activate(label, () => OpenComparisonMenu(label));
            }
            else if (label.Text?.Contains("Chỉ báo", StringComparison.Ordinal) == true)
            {
                ToolTip.SetTip(label, "Bật / tắt EMA 10, EMA 20 và EMA 50 tính từ nến đã đóng.");
                Activate(label, () =>
                {
                    _showIndicators = !_showIndicators;
                    label.Foreground = _showIndicators ? Brush("#4BCBFF") : MutedBrush;
                    InvalidateVisual();
                });
            }
            else if (label.Text == "Nến Nhật")
            {
                ToolTip.SetTip(label, "Chuyển giữa nến OHLC và đường giá đóng cửa.");
                Activate(label, () =>
                {
                    _lineMode = !_lineMode;
                    label.Text = _lineMode ? "Đường giá" : "Nến Nhật";
                    InvalidateVisual();
                });
            }
        }
        UpdateToolbar();
    }

    private static void Activate(Control control, Action action)
    {
        control.Cursor = new Cursor(StandardCursorType.Hand);
        control.Focusable = true;
        control.PointerPressed += (_, e) =>
        {
            if (!e.GetCurrentPoint(control).Properties.IsLeftButtonPressed) return;
            action();
            e.Handled = true;
        };
        control.KeyDown += (_, e) =>
        {
            if (e.Key is not (Key.Enter or Key.Space)) return;
            action();
            e.Handled = true;
        };
    }

    private void OpenComparisonMenu(Control owner)
    {
        var menu = new ContextMenu();
        var clear = new MenuItem { Header = "Tắt so sánh" };
        clear.Click += (_, _) => SetComparisonTimeframe(null);
        menu.Items.Add(clear);
        foreach (var tf in Timeframes.Where(tf => tf != _timeframe))
        {
            var item = new MenuItem
            {
                Header = $"{(_comparisonTimeframe == tf ? "✓ " : "")}{_symbol ?? "Symbol"} {tf} (chuẩn hóa)",
                IsEnabled = _history.TryGetValue(tf, out var bars) && bars.Count > 1
            };
            item.Click += (_, _) => SetComparisonTimeframe(tf);
            menu.Items.Add(item);
        }
        menu.Open(owner);
    }

    private void UpdateToolbar()
    {
        if (_timeframeTitle is not null) _timeframeTitle.Text = _timeframe;
        foreach (var (chip, tf) in _timeframeChips)
        {
            bool available = _history.TryGetValue(tf, out var bars) && bars.Count > 0;
            chip.Background = tf == _timeframe ? Brush("#0866F4") : _chipBackgrounds[chip];
            chip.BorderBrush = Brush(tf == _timeframe ? "#2A8EFF" : "#123D5D");
            ToolTip.SetTip(chip, available ? $"{_symbol} • {tf} • {bars!.Count} nến đã nhận" : $"{tf}: đang chờ lịch sử từ MT5");
        }
    }
    private static readonly IBrush GridBrush = Brush("#123348");
    private static readonly IBrush MutedBrush = Brush("#94B6D2");
    private static readonly IBrush UpBrush = Brush("#00CF88");
    private static readonly IBrush DownBrush = Brush("#FF3658");

    public void SetSnapshot(OverviewSnapshot snapshot, string? timeframe = null)
    {
        if (!string.Equals(_symbol, snapshot.Symbol, StringComparison.OrdinalIgnoreCase) && snapshot.Available)
        {
            _history.Clear();
            _symbol = snapshot.Symbol;
        }
        if (!_userSelectedTimeframe && !string.IsNullOrWhiteSpace(timeframe)) _timeframe = timeframe;
        _connected = snapshot.Available && snapshot.TerminalConnected;
        _bid = _connected ? snapshot.Bid : null;
        if (snapshot.Available)
        {
            foreach (var (tf, history) in snapshot.BarHistory)
            {
                if (!_history.TryGetValue(tf, out var bars)) _history[tf] = bars = new();
                foreach (var bar in history)
                    if (Valid(bar)) bars[bar.Time] = bar;
                while (bars.Count > 180) bars.Remove(bars.Keys.First());
            }
            foreach (var (tf, bar) in snapshot.Bars)
            {
                if (!Valid(bar)) continue;
                if (!_history.TryGetValue(tf, out var bars)) _history[tf] = bars = new();
                bars[bar.Time] = bar;
                while (bars.Count > 180) bars.Remove(bars.Keys.First());
            }
        }
        UpdateToolbar();
        InvalidateVisual();
    }

    public override void Render(DrawingContext context)
    {
        base.Render(context);
        if (Bounds.Width < 90 || Bounds.Height < 60) return;
        context.DrawRectangle(Brush("#041622"), null, new Rect(Bounds.Size));
        var plot = new Rect(1, 30, Bounds.Width - 74, Bounds.Height - 55);
        var pricePlot = new Rect(plot.X, plot.Y, plot.Width, plot.Height * .84);
        var gridPen = new Pen(GridBrush, .7);
        for (var i = 0; i <= 6; i++)
        {
            var x = plot.X + plot.Width * i / 6;
            var y = pricePlot.Y + pricePlot.Height * i / 6;
            context.DrawLine(gridPen, new Point(x, plot.Y), new Point(x, plot.Bottom));
            context.DrawLine(gridPen, new Point(plot.X, y), new Point(plot.Right, y));
        }
        context.DrawLine(new Pen(Brush("#57718A"), .8), plot.TopRight, plot.BottomRight);
        context.DrawLine(new Pen(Brush("#57718A"), .8), plot.BottomLeft, plot.BottomRight);
        var bars = _history.TryGetValue(_timeframe, out var history) ? history.Values.TakeLast(64).ToArray() : [];
        if (bars.Length == 0)
        {
            DrawText(context, "O —    H —    L —    C —", 11, 8, 6, MutedBrush);
            var message = "Đang chờ dữ liệu nến từ MT5";
            var text = Text(message, 13, MutedBrush);
            context.DrawText(text, new Point(Math.Max(8, (plot.Width - text.Width) / 2), plot.Y + plot.Height / 2));
            return;
        }

        var last = bars[^1];
        DrawText(context, $"O {last.Open:N2}    H {last.High:N2}    L {last.Low:N2}    C {last.Close:N2}", 11, 8, 6, Brushes.White);
        double min = bars.Min(b => b.Low), max = bars.Max(b => b.High);
        if (_bid.HasValue) { min = Math.Min(min, _bid.Value); max = Math.Max(max, _bid.Value); }
        var padding = Math.Max((max - min) * .15, .15);
        min -= padding;
        max += padding;
        double Y(double value) => pricePlot.Bottom - (value - min) / (max - min) * pricePlot.Height;
        for (int i = 0; i <= 6; i++)
            DrawText(context, (max - (max - min) * i / 6).ToString("N2", CultureInfo.InvariantCulture), 10, plot.Right + 7, pricePlot.Y + pricePlot.Height * i / 6 - 6, MutedBrush);

        var slot = plot.Width / 66;
        var bodyWidth = Math.Max(2, slot * .68);
        var start = plot.Right - slot * (bars.Length + 1);
        var maxVolume = Math.Max(1, bars.Max(b => b.TickVolume));
        for (int i = 0; i < bars.Length; i++)
        {
            var bar = bars[i];
            var x = start + i * slot;
            var color = bar.Close >= bar.Open ? UpBrush : DownBrush;
            if (!_lineMode)
            {
                context.DrawLine(new Pen(color, 1), new Point(x, Y(bar.High)), new Point(x, Y(bar.Low)));
                context.DrawRectangle(color, null, new Rect(x - bodyWidth / 2, Math.Min(Y(bar.Open), Y(bar.Close)), bodyWidth, Math.Max(1.3, Math.Abs(Y(bar.Open) - Y(bar.Close)))));
            }
            else if (i > 0)
                context.DrawLine(new Pen(Brush("#20B6FF"), 1.5), new Point(x - slot, Y(bars[i - 1].Close)), new Point(x, Y(bar.Close)));
            var height = Math.Max(1, bar.TickVolume / (double)maxVolume * plot.Height * .13);
            context.DrawRectangle(color, null, new Rect(x - bodyWidth / 2, plot.Bottom - height, bodyWidth, height));
            if (i == 0 || i == bars.Length - 1 || (i % 12 == 0 && bars.Length > 20))
            {
                var stamp = DateTimeOffset.FromUnixTimeSeconds(bar.Time).ToString("dd MMM HH:mm", CultureInfo.InvariantCulture);
                DrawText(context, stamp, 10, Math.Clamp(x - 30, 3, Math.Max(3, plot.Right - 76)), plot.Bottom + 6, MutedBrush);
            }
        }
        if (_showIndicators)
        {
            DrawEma(context, bars, 10, start, slot, Y, Brush("#00B9FF"));
            DrawEma(context, bars, 20, start, slot, Y, Brush("#FFAD00"));
            DrawEma(context, bars, 50, start, slot, Y, Brush("#F000E8"));
        }
        DrawComparison(context, bars, start, slot, pricePlot, Y);

        if (_bid is { } bid)
        {
            var y = Y(bid);
            context.DrawLine(new Pen(DownBrush, .8), new Point(plot.X, y), new Point(plot.Right, y));
            context.DrawRectangle(DownBrush, null, new Rect(plot.Right, y - 11, 72, 22));
            DrawText(context, bid.ToString("N2", CultureInfo.InvariantCulture), 11, plot.Right + 5, y - 8, Brushes.White);
        }
        if (!_connected) DrawText(context, "Mất kết nối • dữ liệu gần nhất", 11, 8, 25, Brush("#FFD34D"));
        else if (bars.Length < 10) DrawText(context, $"{_timeframe} • {bars.Length} nến đã nhận", 10, 8, 25, MutedBrush);
    }

    private void DrawComparison(DrawingContext context, MarketBar[] selected, double start, double slot, Rect clip, Func<double, double> y)
    {
        if (_comparisonTimeframe is null || !_history.TryGetValue(_comparisonTimeframe, out var history)) return;
        var comparison = history.Values.Where(b => b.Time >= selected[0].Time && b.Time <= selected[^1].Time).ToArray();
        var color = Brush("#FFD55A");
        DrawText(context, comparison.Length < 2 ? $"{_comparisonTimeframe}: chưa đủ nến trong khoảng này" : $"{_comparisonTimeframe} chuẩn hóa • EMA {(_showIndicators ? "bật" : "tắt")}", 11, 8, 25, color);
        if (comparison.Length < 2 || comparison[0].Close == 0 || selected.Length < 2) return;
        double scale = selected[0].Close / comparison[0].Close;
        double timeSpan = selected[^1].Time - selected[0].Time;
        if (timeSpan <= 0) return;
        Point Project(MarketBar b) => new(start + (b.Time - selected[0].Time) / timeSpan * (selected.Length - 1) * slot, y(b.Close * scale));
        using (context.PushClip(clip))
            for (int i = 1; i < comparison.Length; i++)
                context.DrawLine(new Pen(color, 1.5), Project(comparison[i - 1]), Project(comparison[i]));
    }

    private static void DrawEma(DrawingContext context, MarketBar[] bars, int period, double start, double slot, Func<double, double> y, IBrush brush)
    {
        if (bars.Length < period) return;
        var average = bars.Take(period).Average(b => b.Close);
        var previous = new Point(start + (period - 1) * slot, y(average));
        for (int i = period; i < bars.Length; i++)
        {
            average += (bars[i].Close - average) * 2 / (period + 1);
            var point = new Point(start + i * slot, y(average));
            context.DrawLine(new Pen(brush, 1.1), previous, point);
            previous = point;
        }
    }

    private static bool Valid(MarketBar bar) => bar.Time > 0 && bar.Time < 253402300799 &&
        double.IsFinite(bar.Open) && double.IsFinite(bar.Close) && double.IsFinite(bar.High) && double.IsFinite(bar.Low) &&
        bar.Low <= Math.Min(bar.Open, bar.Close) && bar.High >= Math.Max(bar.Open, bar.Close);
    private static IBrush Brush(string color) => new SolidColorBrush(Color.Parse(color));
    private static FormattedText Text(string value, double size, IBrush brush) => new(value, CultureInfo.InvariantCulture, FlowDirection.LeftToRight, new Typeface("Segoe UI"), size, brush);
    private static void DrawText(DrawingContext context, string value, double size, double x, double y, IBrush brush) => context.DrawText(Text(value, size, brush), new Point(x, y));
}
