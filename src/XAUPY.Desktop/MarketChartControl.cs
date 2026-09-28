using System.Globalization;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Media;
using Avalonia.VisualTree;
using XAUPY.Ipc;

namespace XAUPY.Desktop;

/// <summary>A price chart of closed bars actually received from the MT5 bridge.</summary>
public sealed partial class MarketChartControl : Control
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
    private static readonly string[] Timeframes = ["M1", "M3", "M5", "M15", "M30", "H1", "H2", "H4", "D1"];

    public string SelectedTimeframe => _timeframe;
    public string? ComparisonTimeframe => _comparisonTimeframe;
    public bool ShowIndicators => _showIndicators;

    public void SelectTimeframe(string timeframe)
    {
        if (!Timeframes.Contains(timeframe, StringComparer.OrdinalIgnoreCase)) return;
        _timeframe = timeframe.ToUpperInvariant();
        _panBars=0;
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
            if (label.Name=="ChartCompareAction" || label.Text?.Contains("So sánh", StringComparison.Ordinal) == true)
            {
                ToolTip.SetTip(label, "So sánh khung thời gian hoặc tải lịch sử tài sản khác; chuẩn hóa theo giá đầu khoảng hiển thị.");
                Activate(label, () => OpenComparisonMenu(label));
            }
            else if (label.Name=="ChartIndicatorsAction" || label.Text?.Contains("Chỉ báo", StringComparison.Ordinal) == true)
            {
                ToolTip.SetTip(label, "Cài chu kỳ EMA, RSI, Z và bật/tắt chỉ báo.");
                Activate(label, () => _=RunChartActionAsync(ConfigureIndicatorsAsync));
            }
            else if (label.Name=="ChartStyleAction" || label.Text == "Nến Nhật")
            {
                ToolTip.SetTip(label, "Chuyển giữa nến OHLC và đường giá đóng cửa.");
                Activate(label, () =>
                {
                    _lineMode = !_lineMode;
                    label.Text = LocalizationService.T(_lineMode ? "Đường giá" : "Nến Nhật");
                    InvalidateVisual();
                });
            }
        }
        foreach (var action in panel.GetVisualDescendants().OfType<Control>())
        {
            if (action.Name == "ChartSaveAction") Activate(action,()=>_=RunChartActionAsync(SaveChartAsync));
            else if (action.Name == "ChartFullScreenAction") Activate(action,()=>_=RunChartActionAsync(ShowFullScreenAsync));
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
        clear.Click += (_, _) => { _comparisonBars=null; SetComparisonTimeframe(null); };
        menu.Items.Add(clear);
        var file=new MenuItem { Header="Tải lịch sử tài sản khác…" };
        file.Click+=async (_,_)=>await RunChartActionAsync(()=>LoadHistoryFileAsync(comparison:true)); menu.Items.Add(file);
        foreach (var tf in Timeframes.Where(tf => tf != _timeframe))
        {
            var item = new MenuItem
            {
                Header = $"{(_comparisonTimeframe == tf ? "✓ " : "")}{_symbol ?? "Symbol"} {tf} (chuẩn hóa)",
                IsEnabled = _history.TryGetValue(tf, out var bars) && bars.Count > 1
            };
            item.Click += (_, _) => { _comparisonBars=null; SetComparisonTimeframe(tf); };
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

    private IReadOnlyDictionary<string, MarketBar> _formingBars = new Dictionary<string, MarketBar>();
    public void SetSnapshot(OverviewSnapshot snapshot, string? timeframe = null)
    {
        _latestSnapshot=snapshot;
        _fullScreenChart?.SetSnapshot(snapshot,timeframe);
        if (_archiveMode) return;
        if (!string.Equals(_symbol, snapshot.Symbol, StringComparison.OrdinalIgnoreCase) && snapshot.Available)
        {
            _history.Clear();
            _symbol = snapshot.Symbol;
        }
        if (!_userSelectedTimeframe && !string.IsNullOrWhiteSpace(timeframe)) _timeframe = timeframe;
        _connected = snapshot.Available && snapshot.TerminalConnected;
        _formingBars = _connected ? snapshot.FormingBars : new Dictionary<string, MarketBar>();
        ToolTip.SetTip(this, "Nến cuối cập nhật theo tick đã nhận; OHLC và volume của nến này chỉ phản ánh phần đã quan sát.");
        _bid = _connected ? snapshot.Bid : null;
        if (snapshot.Available)
        {
            foreach (var (tf, history) in snapshot.BarHistory)
            {
                if (!_history.TryGetValue(tf, out var bars)) _history[tf] = bars = new();
                foreach (var bar in history)
                    if (Valid(bar)) bars[bar.Time] = bar;
            }
            foreach (var (tf, bar) in snapshot.Bars)
            {
                if (!Valid(bar)) continue;
                if (!_history.TryGetValue(tf, out var bars)) _history[tf] = bars = new();
                bars[bar.Time] = bar;
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
        var allBars = _history.TryGetValue(_timeframe, out var history) ? history.Values.ToArray() : [];
        if (_formingBars.TryGetValue(_timeframe, out var forming) && Valid(forming) &&
            (allBars.Length == 0 || forming.Time > allBars[^1].Time))
            allBars = [..allBars, forming];
        _panBars=Math.Clamp(_panBars,0,Math.Max(0,allBars.Length-10));
        allBars=allBars.Take(allBars.Length-_panBars).ToArray();
        var bars = allBars.TakeLast(_visibleBars).ToArray();
        double captionSize = Bounds.Width >= 550 ? 14 : 11;
        if (bars.Length == 0)
        {
            DrawText(context, "O —    H —    L —    C —", captionSize, 8, 6, MutedBrush);
            var message = "Đang chờ dữ liệu nến từ MT5";
            var text = Text(message, 13, MutedBrush);
            context.DrawText(text, new Point(Math.Max(8, (plot.Width - text.Width) / 2), plot.Y + plot.Height / 2));
            return;
        }

        var last = bars[^1];
        DrawText(context, FormattableString.Invariant($"O {last.Open:N2}    H {last.High:N2}    L {last.Low:N2}    C {last.Close:N2}"), captionSize, 8, 6, Brushes.White);
        double min = bars.Min(b => b.Low), max = bars.Max(b => b.High);
        if (_panBars==0 && _bid.HasValue) { min = Math.Min(min, _bid.Value); max = Math.Max(max, _bid.Value); }
        var padding = Math.Max((max - min) * .15, .15);
        min -= padding;
        max += padding;
        double Y(double value) => pricePlot.Bottom - (value - min) / (max - min) * pricePlot.Height;
        for (int i = 0; i <= 6; i++)
            DrawText(context, (max - (max - min) * i / 6).ToString("N2", CultureInfo.InvariantCulture), 10, plot.Right + 7, pricePlot.Y + pricePlot.Height * i / 6 - 6, MutedBrush);

        var slot = plot.Width / (_visibleBars+2);
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
        }
        DrawTimeLabels(context, bars, start, slot, plot);
        if (_showIndicators)
        {
            int row = 0;
            foreach (var (period, color) in _emaPeriods.Select((p,i)=>(p,new[]{"#F000E8","#FFAD00","#00B9FF"}[i%3])))
            {
                double? value;
                using (context.PushClip(pricePlot))
                    value = DrawEma(context, allBars, bars.Length, period, start, slot, Y, Brush(color));
                var legend = $"EMA {period}   {value?.ToString("N2", CultureInfo.InvariantCulture) ?? "—"}";
                DrawText(context, legend, captionSize, 8, 37 + row++ * (captionSize + 8), Brush(color));
            }
            var metrics=ChartMetrics(allBars,_rsiPeriod,_zPeriod);
            DrawText(context,$"RSI {_rsiPeriod}: {metrics.Rsi?.ToString("0.00") ?? "—"}  •  Z {_zPeriod}: {metrics.Z?.ToString("0.00") ?? "—"}",11,8,pricePlot.Bottom-34,Brush("#86DCE5"));
        }
        DrawComparison(context, bars, start, slot, pricePlot, Y);

        if (_panBars==0 && _bid is { } bid)
        {
            var y = Y(bid);
            context.DrawLine(new Pen(DownBrush, .8), new Point(plot.X, y), new Point(plot.Right, y));
            context.DrawRectangle(DownBrush, null, new Rect(plot.Right, y - 11, 72, 22));
            DrawText(context, bid.ToString("N2", CultureInfo.InvariantCulture), 11, plot.Right + 5, y - 8, Brushes.White);
        }
        // Keep status, oscillator values and comparison caption on separate
        // baselines, including when the chart is displaying imported history.
        if (_archiveMode) DrawText(context, "Lịch sử từ file • chọn Về giá hiện tại để tiếp tục tick", 11, 8, pricePlot.Bottom - 51, Brush("#FFD34D"));
        else if (!_connected) DrawText(context, "Mất kết nối • dữ liệu gần nhất", 11, 8, pricePlot.Bottom - 51, Brush("#FFD34D"));
        else if (bars.Length < 10) DrawText(context, $"{_timeframe} • {bars.Length} nến đã nhận", 10, 8, pricePlot.Bottom - 51, MutedBrush);
    }

    private static void DrawTimeLabels(DrawingContext context, MarketBar[] bars, double start, double slot, Rect plot)
    {
        int ticks = Math.Clamp((int)(plot.Width / 120), 2, 8);
        var lastLabelRight = double.NegativeInfinity;
        for (int tick = 0; tick < ticks; tick++)
        {
            int index = (int)Math.Round(tick * (bars.Length - 1d) / (ticks - 1));
            var stamp = DateTimeOffset.FromUnixTimeSeconds(bars[index].Time).ToString("dd MMM HH:mm", CultureInfo.InvariantCulture);
            var label = Text(stamp, plot.Width >= 500 ? 12 : 10, MutedBrush);
            var left = Math.Clamp(start + index * slot - label.Width / 2, 3, Math.Max(3, plot.Right - label.Width));
            if (left < lastLabelRight + 12) continue;
            context.DrawText(label, new Point(left, plot.Bottom + 5));
            lastLabelRight = left + label.Width;
        }
    }

    private void DrawComparison(DrawingContext context, MarketBar[] selected, double start, double slot, Rect clip, Func<double, double> y)
    {
        IEnumerable<MarketBar>? source=_comparisonBars;
        if(source is null && _comparisonTimeframe is not null && _history.TryGetValue(_comparisonTimeframe,out var history)) source=history.Values;
        if(source is null) return;
        var comparison = source.Where(b => b.Time >= selected[0].Time && b.Time <= selected[^1].Time).ToArray();
        string name=_comparisonBars is null ? _comparisonTimeframe! : _comparisonSymbol ?? "Tài sản";
        var color = Brush("#FFD55A");
        DrawText(context, comparison.Length < 2 ? $"{name}: chưa đủ nến trong khoảng này" : $"{name} chuẩn hóa • EMA {(_showIndicators ? "bật" : "tắt")}", 11, 8, clip.Bottom - 17, color);
        if (comparison.Length < 2 || comparison[0].Close == 0 || selected.Length < 2) return;
        double scale = selected[0].Close / comparison[0].Close;
        double timeSpan = selected[^1].Time - selected[0].Time;
        if (timeSpan <= 0) return;
        Point Project(MarketBar b) => new(start + (b.Time - selected[0].Time) / timeSpan * (selected.Length - 1) * slot, y(b.Close * scale));
        using (context.PushClip(clip))
            for (int i = 1; i < comparison.Length; i++)
                context.DrawLine(new Pen(color, 1.5), Project(comparison[i - 1]), Project(comparison[i]));
    }

    private static double? DrawEma(DrawingContext context, MarketBar[] bars, int visibleCount, int period, double start, double slot, Func<double, double> y, IBrush brush)
    {
        if (bars.Length < period) return null;
        int firstVisible = bars.Length - visibleCount;
        var average = bars.Take(period).Average(b => b.Close);
        var previous = new Point(start + (period - 1 - firstVisible) * slot, y(average));
        for (int i = period; i < bars.Length; i++)
        {
            average += (bars[i].Close - average) * 2 / (period + 1);
            var point = new Point(start + (i - firstVisible) * slot, y(average));
            if (i > firstVisible) context.DrawLine(new Pen(brush, 1.1), previous, point);
            previous = point;
        }
        return average;
    }

    private static bool Valid(MarketBar bar) => bar.Time > 0 && bar.Time < 253402300799 &&
        double.IsFinite(bar.Open) && double.IsFinite(bar.Close) && double.IsFinite(bar.High) && double.IsFinite(bar.Low) &&
        bar.Low <= Math.Min(bar.Open, bar.Close) && bar.High >= Math.Max(bar.Open, bar.Close);
    private static IBrush Brush(string color) => new SolidColorBrush(Color.Parse(color));
    private static FormattedText Text(string value, double size, IBrush brush) => new(value, CultureInfo.InvariantCulture, FlowDirection.LeftToRight, new Typeface("Segoe UI"), AppearanceService.Scale(size), brush);
    private static void DrawText(DrawingContext context, string value, double size, double x, double y, IBrush brush) => context.DrawText(Text(value, size, brush), new Point(x, y));
}
