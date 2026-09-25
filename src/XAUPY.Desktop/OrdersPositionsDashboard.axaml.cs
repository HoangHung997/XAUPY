using System.Globalization;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Layout;
using Avalonia.Media;
using XAUPY.Ipc;

namespace XAUPY.Desktop;

public partial class OrdersPositionsDashboard : UserControl
{
    private sealed record RowAction(long Ticket, string Action);

    private const int MaxQuotePoints = 18;
    private readonly List<double> _quotes = new();
    private EngineProcessSupervisor? _supervisor;
    private OrdersPositionsSnapshot _book = OrdersPositionsSnapshot.Empty;
    private ConfigurationSummary _config = ConfigurationSummary.Default;
    private string? _lastSnapshotToken;

    public OrdersPositionsDashboard()
    {
        InitializeComponent();
        RenderAll();
        RenderQuoteChart();
    }

    public void AttachSupervisor(EngineProcessSupervisor supervisor)
    {
        _supervisor = supervisor;
    }

    public void Apply(
        OrdersPositionsSnapshot book,
        OverviewSnapshot overview,
        Mt5BridgeStatus bridge,
        ConfigurationSummary config)
    {
        _book = book;
        _config = config;

        if (book.Available &&
            book.Bid.HasValue &&
            !string.IsNullOrWhiteSpace(book.SnapshotReceivedUtc) &&
            !string.Equals(_lastSnapshotToken, book.SnapshotReceivedUtc, StringComparison.Ordinal))
        {
            _lastSnapshotToken = book.SnapshotReceivedUtc;
            _quotes.Add(book.Bid.Value);
            while (_quotes.Count > MaxQuotePoints)
                _quotes.RemoveAt(0);
        }
        else if (!book.Available)
        {
            _lastSnapshotToken = null;
            _quotes.Clear();
        }

        RenderAll();
        RenderQuoteChart();

        bool simulationReady =
            book.Available &&
            book.TerminalConnected &&
            string.Equals(book.AccountTradeMode, "DEMO", StringComparison.OrdinalIgnoreCase);

        Button("MarketBuyButton").IsEnabled = simulationReady;
        Button("MarketSellButton").IsEnabled = simulationReady;

        if (!book.Available)
            SetActionStatus("SIMULATION BLOCKED • chờ snapshot MT5 tươi.", Brushes.Gold);
        else if (!simulationReady)
            SetActionStatus("SIMULATION BLOCKED • Task 009 yêu cầu tài khoản DEMO + terminal online.", Brushes.Gold);
    }

    private void RenderAll()
    {
        Text("OpenPlText").Text = Money(_book.OpenPl, _book.AccountCurrency);
        Text("OpenPlPercentText").Text = PercentOfEquity(_book.OpenPl, _book.Equity);

        Text("RealizedPlText").Text = Money(_book.RealizedPl, _book.AccountCurrency);
        Text("RealizedTodayText").Text = $"Hôm nay: {Money(_book.RealizedPl, _book.AccountCurrency)}";

        Text("ExposureText").Text = $"{_book.ExposureLots:0.##} lots";

        Text("RiskText").Text = _book.RiskComplete && _book.RiskPct.HasValue
            ? $"{_book.RiskPct.Value:0.00}%"
            : "—";
        Text("RiskDetailText").Text = _book.RiskComplete && _book.RiskUsd.HasValue
            ? $"≈ {Money(_book.RiskUsd, _book.AccountCurrency)} • server SL"
            : "Không đủ server SL/tick metadata để tính";

        Text("PendingCountText").Text = _book.OrdersCount.ToString();
        Text("PendingTypesText").Text = PendingTypeSummary(_book.Orders);

        Text("PositionsTitleText").Text = $"Vị thế đang mở ({_book.PositionsCount})";
        Text("PendingTitleText").Text = $"Lệnh chờ đang hoạt động ({_book.OrdersCount})";

        Text("OrdersSymbolText").Text = _book.Symbol ?? _config.Symbol;
        Text("OrdersLastPriceText").Text = Price(_book.Bid);
        Text("OrdersBidText").Text = Price(_book.Bid);
        Text("OrdersAskText").Text = Price(_book.Ask);
        Text("BuyPriceText").Text = Price(_book.Ask);
        Text("SellPriceText").Text = Price(_book.Bid);
        Text("ManualSpreadText").Text = _book.SpreadPoints.HasValue
            ? $"Spread: {_book.SpreadPoints.Value:0.##}"
            : "Spread: —";

        RenderPositions();
        RenderPendingOrders();
        RenderDeals();
    }

    private void RenderPositions()
    {
        var host = Panel("PositionsRowsHost");
        host.Children.Clear();

        if (!_book.Available || _book.Positions.Count == 0)
        {
            host.Children.Add(EmptyRow("Không có vị thế strategy-owned trong snapshot MT5 hiện tại."));
            return;
        }

        for (int i = 0; i < _book.Positions.Count; i++)
            host.Children.Add(PositionRow(_book.Positions[i], i));
    }

    private Border PositionRow(PositionSnapshot position, int index)
    {
        var grid = CreateRowGrid(38, 92, 78, 68, 76, 86, 86, 76, 76, 96, 86, 92, 126, null);

        AddCell(grid, 0, (index + 1).ToString());
        AddCell(grid, 1, position.Ticket.ToString());
        AddCell(grid, 2, position.Symbol);
        AddCell(grid, 3, position.Side, SideBrush(position.Side));
        AddCell(grid, 4, position.Volume.ToString("0.00"));
        AddCell(grid, 5, Price(position.PriceOpen));
        AddCell(grid, 6, Price(position.PriceCurrent));
        AddCell(grid, 7, PriceOrDash(position.Sl));
        AddCell(grid, 8, PriceOrDash(position.Tp));

        double totalPl = position.Profit + position.Swap;
        AddCell(grid, 9, totalPl.ToString("+0.00;-0.00;0.00"), ProfitBrush(totalPl));
        AddCell(grid, 10, PositionPips(position), ProfitBrush(PositionPipsValue(position)));
        AddCell(grid, 11, "Đang mở", Brushes.LightGreen);
        AddCell(grid, 12, Epoch(position.Time));

        var actions = new StackPanel
        {
            Orientation = Orientation.Horizontal,
            Spacing = 4,
            HorizontalAlignment = HorizontalAlignment.Center
        };
        actions.Children.Add(ActionButton("Đóng", position.Ticket, "CLOSE_POSITION"));
        actions.Children.Add(ActionButton("1/2", position.Ticket, "PARTIAL_CLOSE"));
        actions.Children.Add(ActionButton("BE", position.Ticket, "MOVE_SL_BE"));
        actions.Children.Add(ActionButton("TS", position.Ticket, "START_TRAILING"));
        Grid.SetColumn(actions, 13);
        grid.Children.Add(actions);

        return RowBorder(grid, index);
    }

    private void RenderPendingOrders()
    {
        var host = Panel("PendingRowsHost");
        host.Children.Clear();

        if (!_book.Available || _book.Orders.Count == 0)
        {
            host.Children.Add(EmptyRow("Không có pending order strategy-owned trong snapshot MT5 hiện tại."));
            return;
        }

        for (int i = 0; i < _book.Orders.Count; i++)
            host.Children.Add(PendingOrderRow(_book.Orders[i], i));
    }

    private Border PendingOrderRow(PendingOrderSnapshot order, int index)
    {
        var grid = CreateRowGrid(38, 92, 82, 92, 74, 92, 78, 78, 120, 100, 130, null);

        AddCell(grid, 0, (index + 1).ToString());
        AddCell(grid, 1, order.Ticket.ToString());
        AddCell(grid, 2, order.Symbol);
        AddCell(grid, 3, order.Type, SideBrush(order.Type));
        AddCell(grid, 4, order.VolumeCurrent.ToString("0.00"));
        AddCell(grid, 5, Price(order.PriceOpen));
        AddCell(grid, 6, PriceOrDash(order.Sl));
        AddCell(grid, 7, PriceOrDash(order.Tp));
        AddCell(grid, 8, PendingDistance(order));
        AddCell(grid, 9, order.State);
        AddCell(grid, 10, Epoch(order.TimeSetup));

        var actions = new StackPanel
        {
            Orientation = Orientation.Horizontal,
            Spacing = 5,
            HorizontalAlignment = HorizontalAlignment.Center
        };
        actions.Children.Add(ActionButton("✎ Sửa", order.Ticket, "MODIFY_PENDING"));
        actions.Children.Add(ActionButton("✕ Hủy", order.Ticket, "CANCEL_PENDING", danger: true));
        Grid.SetColumn(actions, 11);
        grid.Children.Add(actions);

        return RowBorder(grid, index);
    }

    private void RenderDeals()
    {
        var host = Panel("DealsRowsHost");
        host.Children.Clear();

        if (!_book.Available || _book.Deals.Count == 0)
        {
            host.Children.Add(EmptyRow("Chưa có realized deal strategy-owned trong history MT5."));
            return;
        }

        for (int i = 0; i < _book.Deals.Count; i++)
            host.Children.Add(DealRow(_book.Deals[i], i));
    }

    private Border DealRow(DealSnapshot deal, int index)
    {
        var grid = CreateRowGrid(92, 145, 86, 70, 76, 94, 94, 100, 94, 92, 90, null);

        AddCell(grid, 0, deal.Ticket.ToString());
        AddCell(grid, 1, Epoch(deal.Time));
        AddCell(grid, 2, deal.Symbol);
        AddCell(grid, 3, deal.Side, SideBrush(deal.Side));
        AddCell(grid, 4, deal.Volume.ToString("0.00"));
        AddCell(grid, 5, PriceOrDash(deal.PriceIn));
        AddCell(grid, 6, Price(deal.PriceOut));
        AddCell(grid, 7, deal.RealizedTotal.ToString("+0.00;-0.00;0.00"), ProfitBrush(deal.RealizedTotal));
        AddCell(grid, 8, deal.Commission.ToString("0.00"));
        AddCell(grid, 9, deal.Swap.ToString("0.00"));
        AddCell(grid, 10, $"{deal.Reason} {deal.Comment}".Trim());

        return RowBorder(grid, index);
    }

    private async void RowAction_OnClick(object? sender, RoutedEventArgs e)
    {
        if (sender is not Button { Tag: RowAction tag })
            return;

        if (tag.Action == "MODIFY_PENDING")
        {
            await ModifyPendingAsync(tag.Ticket);
            return;
        }

        double? percent = tag.Action == "PARTIAL_CLOSE" ? 50.0 : null;
        await SendActionAsync(
            tag.Action,
            confirmed: Check("ConfirmCloseCheck").IsChecked == true,
            ticket: tag.Ticket,
            percent: percent);
    }

    private async void BulkAction_OnClick(object? sender, RoutedEventArgs e)
    {
        if (sender is not Button { Tag: string action })
            return;

        bool confirmed = Check("ConfirmCloseCheck").IsChecked == true;

        switch (action)
        {
            case "PARTIAL_ALL":
                await ExecuteAcrossPositionsAsync("PARTIAL_CLOSE", confirmed, percent: 50);
                break;
            case "BE_ALL":
                await ExecuteAcrossPositionsAsync("MOVE_SL_BE", confirmed);
                break;
            case "TRAIL_ALL":
                await ExecuteAcrossPositionsAsync("START_TRAILING", confirmed);
                break;
            default:
                await SendActionAsync(action, confirmed);
                break;
        }
    }

    private async Task ExecuteAcrossPositionsAsync(
        string action,
        bool confirmed,
        double? percent = null)
    {
        if (_book.Positions.Count == 0)
        {
            SetActionStatus("REJECTED • không có position để mô phỏng.", Brushes.IndianRed);
            return;
        }

        int accepted = 0;
        string lastCode = string.Empty;

        foreach (var position in _book.Positions)
        {
            var result = await SendActionAsync(
                action,
                confirmed,
                ticket: position.Ticket,
                percent: percent,
                updateStatus: false);
            if (result?.Accepted == true)
                accepted++;
            if (result is not null)
                lastCode = result.Code;
        }

        SetActionStatus(
            $"SIMULATED • {action}: {accepted}/{_book.Positions.Count} accepted • {lastCode}",
            accepted == _book.Positions.Count ? Brushes.LightGreen : Brushes.Gold);
    }

    private async void MarketBuy_OnClick(object? sender, RoutedEventArgs e) =>
        await SendMarketAsync("MARKET_BUY");

    private async void MarketSell_OnClick(object? sender, RoutedEventArgs e) =>
        await SendMarketAsync("MARKET_SELL");

    private async Task SendMarketAsync(string action)
    {
        if (!TryNumber(Box("ManualLotBox").Text, out var volume))
        {
            SetActionStatus("REJECTED • Lot không hợp lệ.", Brushes.IndianRed);
            return;
        }

        double? slPoints = NullableNumber(Box("ManualSlBox").Text);
        double? tpPoints = NullableNumber(Box("ManualTpBox").Text);

        await SendActionAsync(
            action,
            confirmed: Check("ManualConfirmCheck").IsChecked == true,
            volume: volume,
            slPoints: slPoints,
            tpPoints: tpPoints);
    }

    private void QuickLot_OnClick(object? sender, RoutedEventArgs e)
    {
        if (sender is Button { Tag: string lot })
            Box("ManualLotBox").Text = lot;
    }

    private async Task ModifyPendingAsync(long ticket)
    {
        var order = _book.Orders.FirstOrDefault(item => item.Ticket == ticket);
        if (order is null)
        {
            SetActionStatus("REJECTED • pending ticket không còn trong snapshot.", Brushes.IndianRed);
            return;
        }

        var owner = TopLevel.GetTopLevel(this) as Window;
        if (owner is null)
        {
            SetActionStatus("REJECTED • không tạo được cửa sổ sửa lệnh.", Brushes.IndianRed);
            return;
        }

        var priceBox = new TextBox { Text = Price(order.PriceOpen), PlaceholderText = "Giá đặt" };
        var slBox = new TextBox { Text = PriceOrDash(order.Sl).Replace("—", ""), PlaceholderText = "SL" };
        var tpBox = new TextBox { Text = PriceOrDash(order.Tp).Replace("—", ""), PlaceholderText = "TP" };
        var confirm = new CheckBox { Content = "Xác nhận mô phỏng sửa pending order" };
        var status = new TextBlock { Foreground = Brushes.Gold, TextWrapping = TextWrapping.Wrap };
        var ok = new Button { Content = "Mô phỏng sửa", Classes = { "primary" } };
        var cancel = new Button { Content = "Hủy", Classes = { "secondary" } };

        var buttons = new StackPanel
        {
            Orientation = Orientation.Horizontal,
            Spacing = 8,
            HorizontalAlignment = HorizontalAlignment.Right
        };
        buttons.Children.Add(cancel);
        buttons.Children.Add(ok);

        var content = new StackPanel { Margin = new Thickness(16), Spacing = 8 };
        content.Children.Add(new TextBlock { Text = $"Pending #{ticket}", FontSize = 18, FontWeight = FontWeight.SemiBold });
        content.Children.Add(new TextBlock { Text = "Giá đặt", Foreground = Brushes.LightGray });
        content.Children.Add(priceBox);
        content.Children.Add(new TextBlock { Text = "SL", Foreground = Brushes.LightGray });
        content.Children.Add(slBox);
        content.Children.Add(new TextBlock { Text = "TP", Foreground = Brushes.LightGray });
        content.Children.Add(tpBox);
        content.Children.Add(confirm);
        content.Children.Add(status);
        content.Children.Add(buttons);

        var dialog = new Window
        {
            Width = 430,
            Height = 390,
            MinWidth = 430,
            MinHeight = 390,
            Title = "XAUPY • Mô phỏng sửa lệnh chờ",
            Background = new SolidColorBrush(Color.Parse("#031426")),
            Content = content,
            CanResize = false
        };

        (double? Price, double? Sl, double? Tp, bool Confirmed)? result = null;

        cancel.Click += (_, _) => dialog.Close();
        ok.Click += (_, _) =>
        {
            if (!TryNumber(priceBox.Text, out var price))
            {
                status.Text = "Giá đặt không hợp lệ.";
                return;
            }

            result = (
                price,
                NullableNumber(slBox.Text),
                NullableNumber(tpBox.Text),
                confirm.IsChecked == true);
            dialog.Close();
        };

        await dialog.ShowDialog(owner);

        if (result is not { } change)
            return;

        await SendActionAsync(
            "MODIFY_PENDING",
            change.Confirmed,
            ticket: ticket,
            price: change.Price,
            sl: change.Sl,
            tp: change.Tp);
    }

    private async Task<ManualActionResult?> SendActionAsync(
        string action,
        bool confirmed,
        long? ticket = null,
        double? volume = null,
        double? slPoints = null,
        double? tpPoints = null,
        double? percent = null,
        double? price = null,
        double? sl = null,
        double? tp = null,
        bool updateStatus = true)
    {
        if (_supervisor is null)
        {
            if (updateStatus)
                SetActionStatus("REJECTED • Engine supervisor chưa gắn.", Brushes.IndianRed);
            return null;
        }

        try
        {
            var result = await _supervisor.SimulateManualActionAsync(
                action,
                confirmed,
                ticket,
                volume,
                slPoints,
                tpPoints,
                percent,
                price,
                sl,
                tp);

            if (updateStatus)
            {
                string prefix = result.Accepted ? "SIMULATED" : "REJECTED";
                SetActionStatus(
                    $"{prefix} • {result.Code} • {result.Message}",
                    result.Accepted ? Brushes.LightGreen : Brushes.IndianRed);
            }

            return result;
        }
        catch (Exception ex)
        {
            if (updateStatus)
                SetActionStatus($"ERROR • {ex.Message}", Brushes.IndianRed);
            return null;
        }
    }

    private void RenderQuoteChart()
    {
        var host = Panel("OrdersChartBars");
        host.Children.Clear();

        if (_quotes.Count == 0)
        {
            for (int i = 0; i < MaxQuotePoints; i++)
                host.Children.Add(QuoteBar(18, Brushes.SlateGray, 0.25));

            Text("OrdersChartLastText").Text = "—";
            Text("OrdersChangeText").Text = "—";
            return;
        }

        double min = _quotes.Min();
        double max = _quotes.Max();
        double range = Math.Max(max - min, 0.000001);
        int blank = MaxQuotePoints - _quotes.Count;

        for (int i = 0; i < MaxQuotePoints; i++)
        {
            if (i < blank)
            {
                host.Children.Add(QuoteBar(18, Brushes.SlateGray, 0.20));
                continue;
            }

            int source = i - blank;
            double value = _quotes[source];
            double normalized = (value - min) / range;
            double height = 24 + normalized * 165;
            bool up = source == 0 || value >= _quotes[source - 1];
            host.Children.Add(QuoteBar(
                height,
                up ? Brushes.MediumSpringGreen : Brushes.IndianRed,
                0.90));
        }

        double last = _quotes[^1];
        double first = _quotes[0];
        double delta = last - first;
        double pct = Math.Abs(first) > 1e-9 ? delta / first * 100.0 : 0.0;

        Text("OrdersChartLastText").Text = last.ToString("0.00###");
        Text("OrdersChangeText").Text = $"{delta:+0.00;-0.00;0.00} ({pct:+0.00;-0.00;0.00}%)";
        Text("OrdersChangeText").Foreground = delta >= 0 ? Brushes.LightGreen : Brushes.IndianRed;
    }

    private static Border QuoteBar(double height, IBrush brush, double opacity) => new()
    {
        Width = 8,
        Height = height,
        Background = brush,
        Opacity = opacity,
        CornerRadius = new CornerRadius(1),
        VerticalAlignment = VerticalAlignment.Bottom
    };

    private static Grid CreateRowGrid(params double?[] widths)
    {
        var grid = new Grid { MinHeight = 31 };
        foreach (double? width in widths)
        {
            grid.ColumnDefinitions.Add(
                width.HasValue
                    ? new ColumnDefinition(new GridLength(width.Value))
                    : new ColumnDefinition(new GridLength(1, GridUnitType.Star)));
        }

        return grid;
    }

    private static void AddCell(
        Grid grid,
        int column,
        string value,
        IBrush? foreground = null)
    {
        var cell = new TextBlock
        {
            Text = value,
            FontSize = 11,
            Foreground = foreground ?? new SolidColorBrush(Color.Parse("#D7E4F2")),
            VerticalAlignment = VerticalAlignment.Center,
            TextTrimming = TextTrimming.CharacterEllipsis
        };
        Grid.SetColumn(cell, column);
        grid.Children.Add(cell);
    }

    private Button ActionButton(string text, long ticket, string action, bool danger = false)
    {
        var button = new Button
        {
            Content = text,
            Tag = new RowAction(ticket, action),
            Classes = { danger ? "dangerAction" : "rowAction" }
        };
        button.Click += RowAction_OnClick;
        return button;
    }

    private static Border RowBorder(Grid grid, int index) => new()
    {
        Background = new SolidColorBrush(Color.Parse(index % 2 == 0 ? "#06192C" : "#071E34")),
        BorderBrush = new SolidColorBrush(Color.Parse("#123D5D")),
        BorderThickness = new Thickness(0, 1, 0, 0),
        Padding = new Thickness(2, 3),
        Child = grid
    };

    private static Border EmptyRow(string message) => new()
    {
        Background = new SolidColorBrush(Color.Parse("#06192C")),
        Padding = new Thickness(12, 13),
        Child = new TextBlock
        {
            Text = message,
            Foreground = new SolidColorBrush(Color.Parse("#8099B2")),
            HorizontalAlignment = HorizontalAlignment.Center,
            TextWrapping = TextWrapping.Wrap
        }
    };

    private string PositionPips(PositionSnapshot position)
    {
        double value = PositionPipsValue(position);
        return double.IsNaN(value) ? "—" : value.ToString("+0.0;-0.0;0.0");
    }

    private double PositionPipsValue(PositionSnapshot position)
    {
        if (!_book.Point.HasValue || _book.Point.Value <= 0)
            return double.NaN;

        double delta = position.Side.Equals("SELL", StringComparison.OrdinalIgnoreCase)
            ? position.PriceOpen - position.PriceCurrent
            : position.PriceCurrent - position.PriceOpen;
        return delta / _book.Point.Value;
    }

    private string PendingDistance(PendingOrderSnapshot order)
    {
        if (!_book.Point.HasValue || _book.Point.Value <= 0)
            return "—";

        double? current = order.Type.StartsWith("BUY", StringComparison.OrdinalIgnoreCase)
            ? _book.Ask
            : _book.Bid;
        if (!current.HasValue)
            return "—";

        return $"{Math.Abs(order.PriceOpen - current.Value) / _book.Point.Value:0.0} pips";
    }

    private static string PendingTypeSummary(IReadOnlyList<PendingOrderSnapshot> orders)
    {
        if (orders.Count == 0)
            return "—";

        return string.Join(
            "  |  ",
            orders
                .GroupBy(item => item.Type, StringComparer.OrdinalIgnoreCase)
                .OrderBy(group => group.Key, StringComparer.OrdinalIgnoreCase)
                .Select(group => $"{group.Key}: {group.Count()}"));
    }

    private static string Epoch(long value)
    {
        try
        {
            return DateTimeOffset.FromUnixTimeSeconds(value)
                .ToLocalTime()
                .ToString("yyyy.MM.dd HH:mm");
        }
        catch (ArgumentOutOfRangeException)
        {
            return value.ToString();
        }
    }

    private static IBrush SideBrush(string side) =>
        side.StartsWith("BUY", StringComparison.OrdinalIgnoreCase)
            ? Brushes.LightGreen
            : side.StartsWith("SELL", StringComparison.OrdinalIgnoreCase)
                ? Brushes.IndianRed
                : Brushes.LightGray;

    private static IBrush ProfitBrush(double value) =>
        double.IsNaN(value)
            ? Brushes.LightGray
            : value > 0
                ? Brushes.LightGreen
                : value < 0
                    ? Brushes.IndianRed
                    : Brushes.LightGray;

    private static string Price(double value) => value.ToString("0.00###");
    private static string Price(double? value) => value.HasValue ? Price(value.Value) : "—";
    private static string PriceOrDash(double value) => value > 0 ? Price(value) : "—";

    private static string Money(double? value, string? currency)
    {
        if (!value.HasValue)
            return "—";

        string suffix = string.IsNullOrWhiteSpace(currency) ? string.Empty : $" {currency}";
        return $"{value.Value:+0.00;-0.00;0.00}{suffix}";
    }

    private static string PercentOfEquity(double? pl, double? equity)
    {
        if (!pl.HasValue || !equity.HasValue || Math.Abs(equity.Value) < 1e-9)
            return "—";
        return $"{pl.Value / equity.Value * 100.0:+0.00;-0.00;0.00}%";
    }

    private static bool TryNumber(string? text, out double value)
    {
        if (double.TryParse(text, NumberStyles.Float, CultureInfo.InvariantCulture, out value))
            return true;
        return double.TryParse(text, NumberStyles.Float, CultureInfo.CurrentCulture, out value);
    }

    private static double? NullableNumber(string? text)
    {
        if (string.IsNullOrWhiteSpace(text))
            return null;
        return TryNumber(text, out var value) ? value : null;
    }

    private void SetActionStatus(string message, IBrush brush)
    {
        Text("ActionStatusText").Text = message;
        Text("ActionStatusText").Foreground = brush;
    }

    private TextBlock Text(string name) =>
        this.FindControl<TextBlock>(name)
        ?? throw new InvalidOperationException($"Missing OrdersPositions TextBlock: {name}");

    private TextBox Box(string name) =>
        this.FindControl<TextBox>(name)
        ?? throw new InvalidOperationException($"Missing OrdersPositions TextBox: {name}");

    private CheckBox Check(string name) =>
        this.FindControl<CheckBox>(name)
        ?? throw new InvalidOperationException($"Missing OrdersPositions CheckBox: {name}");

    private Button Button(string name) =>
        this.FindControl<Button>(name)
        ?? throw new InvalidOperationException($"Missing OrdersPositions Button: {name}");

    private StackPanel Panel(string name) =>
        this.FindControl<StackPanel>(name)
        ?? throw new InvalidOperationException($"Missing OrdersPositions panel: {name}");
}
