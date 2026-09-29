using System.Globalization;
using System.Text;
using System.Text.Json;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Platform.Storage;
using XAUPY.Ipc;

namespace XAUPY.Desktop;

public partial class BacktestDashboard : UserControl
{
    private bool _controlsReady;
    private void DrawdownUnit_OnChanged(object? sender, SelectionChangedEventArgs e)
    {
        if (!_controlsReady) return; // XAML may raise SelectionChanged before its name scope is attached.
        if(sender is ComboBox {SelectedItem:ComboBoxItem {Tag:string unit}} && this.FindControl<BacktestChartControl>("DrawdownChart") is { } chart)
            chart.SelectDrawdownUnit(unit);
    }

    private const int TradePageSize = 8;

    private static readonly FilePickerFileType BacktestDataFileType = new("XAUPY Historical Data")
    {
        Patterns = new[] { "*.json", "*.csv" }
    };

    private static readonly FilePickerFileType JsonFileType = new("JSON")
    {
        Patterns = new[] { "*.json" }
    };

    private static readonly FilePickerFileType CsvFileType = new("CSV")
    {
        Patterns = new[] { "*.csv" }
    };

    private readonly List<BacktestHistoryItem> _history = new();
    private EngineProcessSupervisor? _supervisor;
    private BacktestDatasetInfo? _dataset;
    private BacktestResultSnapshot? _current;
    private BacktestHistoryItem? _selectedHistory;
    private int _tradePage;
    private bool _loading;
    private CancellationTokenSource? _runCancellation;

    public BacktestDashboard()
    {
        InitializeComponent();
        _controlsReady = true;
        ClearResult();
        RenderHistory();
        RenderTrades();
    }

    public void AttachSupervisor(EngineProcessSupervisor supervisor)
    {
        _supervisor = supervisor;
    }

    public void ApplyConfiguration(ConfigurationSummary config)
    {
        if (_dataset is null)
            Text("BacktestSymbolText").Text = config.Symbol;
    }

    public async Task EnsureLoadedAsync(bool force = false)
    {
        if (_loading || _supervisor is null)
            return;

        if (_supervisor.State != EngineConnectionState.Ready)
        {
            SetStatus("Đang chờ Python Engine READY...", Brushes.Gold);
            return;
        }

        if (!force && _history.Count > 0)
            return;

        await RefreshHistoryAsync();
    }

    private async void LoadDataset_OnClick(object? sender, RoutedEventArgs e)
    {
        await SelectDatasetAsync();
    }

    private async Task<bool> SelectDatasetAsync()
    {
        if (_supervisor is null || _supervisor.State != EngineConnectionState.Ready)
        {
            SetStatus("Python Engine chưa READY.", Brushes.Gold);
            return false;
        }

        var storage = TopLevel.GetTopLevel(this)?.StorageProvider;
        if (storage is null || !storage.CanOpen)
        {
            SetStatus("Storage provider không hỗ trợ mở file.", Brushes.IndianRed);
            return false;
        }

        try
        {
            var path = await HistoryDatasetPicker.PickAsync(this,_supervisor);
            if (path is null) return false;
            _loading = true;
            SetStatus("Đang kiểm tra dataset...", Brushes.LightBlue);
            var info = await _supervisor.InspectBacktestDatasetAsync(path);
            _dataset = info;
            Text("BacktestTimeframeText").Text=info.Timeframe;

            Text("BacktestSymbolText").Text = info.Metadata.Symbol;
            Box("BacktestFromDateBox").Text = info.FirstDate;
            Box("BacktestToDateBox").Text = info.LastDate;
            Text("DatasetStatusText").Text =
                $"Dữ liệu: {info.FileName} • {info.Timeframe} • {info.BarCount:N0} nến • " +
                $"point {info.Metadata.PointSize:0.#####} • tick {info.Metadata.TickSize:0.#####}/{info.Metadata.TickValue:0.#####} • " +
                $"SHA {ShortHash(info.DatasetFingerprint)}";
            SetStatus("Dataset hợp lệ, sẵn sàng Backtest.", Brushes.LightGreen);
            return true;
        }
        catch (Exception ex)
        {
            _dataset = null;
            Text("DatasetStatusText").Text = "Dữ liệu: chưa chọn file M1 JSON/CSV";
            SetStatus($"Dataset bị từ chối: {ex.Message}", Brushes.IndianRed);
            return false;
        }
        finally
        {
            _loading = false;
        }
    }

    private async void RunBacktest_OnClick(object? sender, RoutedEventArgs e)
    {
        if (_loading) return;
        if (_supervisor is null || _supervisor.State != EngineConnectionState.Ready)
        {
            SetStatus("Python Engine chưa READY.", Brushes.Gold);
            return;
        }

        if (_dataset is null && !await SelectDatasetAsync())
            return;

        if (!TryNumber(Box("InitialBalanceBox").Text, out var initialBalance) ||
            initialBalance <= 0)
        {
            SetStatus("Vốn ban đầu phải > 0.", Brushes.IndianRed);
            return;
        }

        if (!TryNumber(Box("BacktestSpreadBox").Text, out var spread) || spread < 0)
        {
            SetStatus("Spread phải >= 0.", Brushes.IndianRed);
            return;
        }

        if (!TryNumber(Box("BacktestCommissionBox").Text, out var commission) || commission < 0)
        {
            SetStatus("Hoa hồng phải >= 0.", Brushes.IndianRed);
            return;
        }

        string fromDate = Box("BacktestFromDateBox").Text?.Trim() ?? string.Empty;
        string toDate = Box("BacktestToDateBox").Text?.Trim() ?? string.Empty;

        if (!DateOnly.TryParseExact(fromDate, "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out _) ||
            !DateOnly.TryParseExact(toDate, "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out _))
        {
            SetStatus("Ngày phải theo định dạng YYYY-MM-DD.", Brushes.IndianRed);
            return;
        }

        try
        {
            _loading = true;
            _runCancellation = new CancellationTokenSource();
            Button("RunBacktestButton").IsEnabled = false;
            Button("CancelBacktestButton").IsEnabled = true;
            SetStatus("Đang chạy Backtest nền; dữ liệu live tiếp tục cập nhật...", Brushes.LightBlue);

            var result = await _supervisor.RunBacktestAsync(
                _dataset!.Path,
                fromDate,
                toDate,
                initialBalance,
                spread,
                commission, _runCancellation.Token,
                new Progress<BacktestJobSnapshot>(job => {
                    if (_runCancellation is { IsCancellationRequested: false } && job.State is "QUEUED" or "RUNNING")
                        SetStatus(job.TotalBars > 0 ? $"Backtest: {job.CompletedBars:N0}/{job.TotalBars:N0} quan sát • {job.State}" : "Đang đọc dữ liệu Backtest...", Brushes.LightBlue);
                }), model: this.FindControl<ComboBox>("BacktestModelCombo")!.SelectedIndex switch {1=>"M1_OHLC",2=>"REAL_TICKS",_=>"AUTO"});

            _tradePage = 0;
            await LoadRunAsync(result.RunId, page: 0);
            SetStatus(
                $"Backtest hoàn thành • hash {ShortHash(result.ResultHash)} • {result.Metrics.TotalTrades} lệnh.",
                Brushes.LightGreen);

            await RefreshHistoryAsync(selectRunId: result.RunId);
        }
        catch (OperationCanceledException)
        {
            SetStatus("Đã yêu cầu hủy Backtest. Kết quả cũ được giữ nguyên.", Brushes.Gold);
        }
        catch (Exception ex)
        {
            SetStatus($"Backtest thất bại: {ex.Message}", Brushes.IndianRed);
        }
        finally
        {
            _loading = false;
            Button("RunBacktestButton").IsEnabled = true;
            Button("CancelBacktestButton").IsEnabled = false;
            _runCancellation?.Dispose();
            _runCancellation = null;
        }
    }

    private void CancelBacktest_OnClick(object? sender, RoutedEventArgs e)
    {
        _runCancellation?.Cancel();
        Button("CancelBacktestButton").IsEnabled = false;
        SetStatus("Đang hủy Backtest...", Brushes.Gold);
    }

    private async void RefreshHistory_OnClick(object? sender, RoutedEventArgs e)
    {
        await RefreshHistoryAsync();
    }

    private async Task RefreshHistoryAsync(string? selectRunId = null)
    {
        if (_supervisor is null || _supervisor.State != EngineConnectionState.Ready)
            return;

        try
        {
            var result = await _supervisor.QueryBacktestHistoryAsync(50);
            if (!result.Ok)
            {
                SetStatus(
                    result.Errors.Count > 0
                        ? string.Join(" • ", result.Errors)
                        : "Không tải được history Backtest.",
                    Brushes.IndianRed);
                return;
            }

            _history.Clear();
            _history.AddRange(result.Items);
            if (!string.IsNullOrWhiteSpace(selectRunId))
                _selectedHistory = _history.FirstOrDefault(item => item.RunId == selectRunId);
            else if (_selectedHistory is not null)
                _selectedHistory = _history.FirstOrDefault(item => item.RunId == _selectedHistory.RunId);
            else
                _selectedHistory = _history.FirstOrDefault();

            RenderHistory();
        }
        catch (Exception ex)
        {
            SetStatus($"History lỗi: {ex.Message}", Brushes.IndianRed);
        }
    }

    private void HistoryRow_OnClick(object? sender, RoutedEventArgs e)
    {
        if (sender is not Button { Tag: string runId })
            return;

        _selectedHistory = _history.FirstOrDefault(item => item.RunId == runId);
        RenderHistory();
    }

    private async void ViewSelectedHistory_OnClick(object? sender, RoutedEventArgs e)
    {
        if (_selectedHistory is null)
        {
            SetStatus("Chưa chọn kết quả Backtest.", Brushes.Gold);
            return;
        }

        await LoadRunAsync(_selectedHistory.RunId, page: 0);
    }

    private async void DeleteSelectedHistory_OnClick(object? sender, RoutedEventArgs e)
    {
        if (_selectedHistory is null)
        {
            SetStatus("Chưa chọn kết quả Backtest.", Brushes.Gold);
            return;
        }

        if (!await ConfirmDeleteAsync(_selectedHistory))
            return;

        try
        {
            var result = await _supervisor!.DeleteBacktestResultAsync(_selectedHistory.RunId);
            if (!result.Ok || !result.Deleted)
            {
                SetStatus(
                    result.Errors.Count > 0
                        ? string.Join(" • ", result.Errors)
                        : "Kết quả không tồn tại hoặc chưa xóa.",
                    Brushes.IndianRed);
                return;
            }

            if (_current?.RunId == _selectedHistory.RunId)
            {
                _current = null;
                ClearResult();
            }

            string deleted = _selectedHistory.RunId;
            _selectedHistory = null;
            await RefreshHistoryAsync();
            SetStatus($"Đã xóa kết quả {ShortHash(deleted)}.", Brushes.LightGreen);
        }
        catch (Exception ex)
        {
            SetStatus($"Xóa kết quả lỗi: {ex.Message}", Brushes.IndianRed);
        }
    }

    private async Task LoadRunAsync(string runId, int page)
    {
        if (_supervisor is null || _supervisor.State != EngineConnectionState.Ready)
            return;

        try
        {
            int offset = Math.Max(0, page) * TradePageSize;
            var result = await _supervisor.GetBacktestResultAsync(
                runId,
                tradeOffset: offset,
                tradeLimit: TradePageSize);
            _tradePage = Math.Max(0, page);
            _current = result;
            ApplyResult(result);
            SetStatus($"Đã tải Backtest {ShortHash(runId)}.", Brushes.LightGreen);
        }
        catch (Exception ex)
        {
            SetStatus($"Không tải được Backtest: {ex.Message}", Brushes.IndianRed);
        }
    }

    private async void PrevTradePage_OnClick(object? sender, RoutedEventArgs e)
    {
        if (_current is null || _tradePage <= 0)
            return;
        await LoadRunAsync(_current.RunId, _tradePage - 1);
    }

    private async void NextTradePage_OnClick(object? sender, RoutedEventArgs e)
    {
        if (_current is null)
            return;

        int pages = Math.Max(1, (int)Math.Ceiling(_current.TradeTotal / (double)TradePageSize));
        if (_tradePage + 1 >= pages)
            return;

        await LoadRunAsync(_current.RunId, _tradePage + 1);
    }

    private async void SaveResult_OnClick(object? sender, RoutedEventArgs e)
    {
        if (_current is null)
        {
            SetStatus("Chưa có kết quả Backtest để lưu.", Brushes.Gold);
            return;
        }

        var storage = TopLevel.GetTopLevel(this)?.StorageProvider;
        if (storage is null || !storage.CanSave)
        {
            SetStatus("Storage provider không hỗ trợ lưu file.", Brushes.IndianRed);
            return;
        }

        var report = _current;
        var file = await storage.SaveFilePickerAsync(
            new FilePickerSaveOptions
            {
                Title = LocalizationService.T("Lưu kết quả Backtest XAUPY"),
                SuggestedFileName = $"XAUPY-Backtest-{_current.FromDate}-{_current.ToDate}.json",
                DefaultExtension = "json",
                FileTypeChoices = new[] { JsonFileType }
            });

        if (file is null)
            return;

        try
        {
            var export = await FetchFullResultAsync(report);

            await FileOutput.WriteTextAsync(file, JsonSerializer.Serialize(export, new JsonSerializerOptions { WriteIndented = true }));

            SetStatus($"Đã lưu kết quả: {file.Name}", Brushes.LightGreen);
        }
        catch (Exception ex)
        {
            SetStatus($"Lưu kết quả lỗi: {ex.Message}", Brushes.IndianRed);
        }
    }

    private async void ExportReport_OnClick(object? sender, RoutedEventArgs e)
    {
        if (_current is null)
        {
            SetStatus("Chưa có kết quả Backtest để xuất.", Brushes.Gold);
            return;
        }

        var storage = TopLevel.GetTopLevel(this)?.StorageProvider;
        if (storage is null || !storage.CanSave)
        {
            SetStatus("Storage provider không hỗ trợ lưu file.", Brushes.IndianRed);
            return;
        }

        var report = _current;
        var file = await storage.SaveFilePickerAsync(
            new FilePickerSaveOptions
            {
                Title = LocalizationService.T("Xuất báo cáo Backtest"),
                SuggestedFileName = $"XAUPY-Backtest-{_current.FromDate}-{_current.ToDate}.html",
                DefaultExtension = "html",
                FileTypeChoices = new[] { new FilePickerFileType("Báo cáo tổng hợp HTML") {Patterns=["*.html"]}, CsvFileType }
            });

        if (file is null)
            return;

        try
        {
            var trades = await FetchAllTradesAsync(report.RunId, report.TradeTotal);
            if(file.Name.EndsWith(".html",StringComparison.OrdinalIgnoreCase))
            {
                await FileOutput.WriteTextAsync(file,BuildHtmlReport(report,trades));
                SetStatus($"Đã xuất báo cáo và {trades.Count} giao dịch: {file.Name}",Brushes.LightGreen);return;
            }
            await using var stream = new MemoryStream();
            await using var writer = new StreamWriter(
                stream,
                new UTF8Encoding(false),
                1024,
                leaveOpen: true);

            await writer.WriteLineAsync(
                "trade_id,signal_sequence,side,entry_time,exit_time,entry_price,exit_price,volume,net_pl,commission,exit_reason,mae_price_units,mfe_price_units,mae_usd,mfe_usd");

            foreach (var trade in trades)
            {
                await writer.WriteLineAsync(string.Join(
                    ",",
                    trade.TradeId,
                    trade.SignalSequence,
                    Csv(trade.Side),
                    trade.EntryTime,
                    trade.ExitTime,
                    Invariant(trade.EntryPrice),
                    Invariant(trade.ExitPrice),
                    Invariant(trade.Volume),
                    Invariant(trade.NetPl),
                    Invariant(trade.Commission),
                    Csv(trade.ExitReason),
                    Invariant(trade.MaePriceUnits),
                    Invariant(trade.MfePriceUnits),
                    Invariant(trade.MaeUsd),
                    Invariant(trade.MfeUsd)));
            }

            await writer.FlushAsync();
            await stream.FlushAsync();
            stream.Position=0;
            await FileOutput.CopyAsync(file,stream);
            SetStatus($"Đã xuất {trades.Count} giao dịch: {file.Name}", Brushes.LightGreen);
        }
        catch (Exception ex)
        {
            SetStatus($"Xuất báo cáo lỗi: {ex.Message}", Brushes.IndianRed);
        }
    }

    private async Task<IReadOnlyList<BacktestTradeSnapshot>> FetchAllTradesAsync(
        string runId,
        int total)
    {
        var result = new List<BacktestTradeSnapshot>();
        int offset = 0;
        while (offset < total)
        {
            int limit = Math.Min(500, total - offset);
            var page = await _supervisor!.GetBacktestResultAsync(
                runId,
                tradeOffset: offset,
                tradeLimit: Math.Max(1, limit));
            result.AddRange(page.Trades);
            if (page.Trades.Count == 0)
                break;
            offset += page.Trades.Count;
        }
        if(result.Count!=total)throw new InvalidDataException("Lịch sử trả về chưa đầy đủ; không xuất báo cáo thiếu giao dịch.");
        return result;
    }

    private async Task<System.Text.Json.Nodes.JsonObject> FetchFullResultAsync(BacktestResultSnapshot report)
    {
        var result = System.Text.Json.Nodes.JsonNode.Parse(report.RawResult.GetRawText())!.AsObject();
        var trades = new System.Text.Json.Nodes.JsonArray();
        while (trades.Count < report.TradeTotal)
        {
            var page = await _supervisor!.GetBacktestResultAsync(report.RunId,
                tradeOffset: trades.Count, tradeLimit: Math.Min(500, report.TradeTotal - trades.Count));
            if (page.ResultHash != report.ResultHash || page.TradeTotal != report.TradeTotal)
                throw new InvalidDataException("Kết quả đã thay đổi trong lúc xuất.");
            var received = page.RawResult.GetProperty("trades");
            if (received.GetArrayLength() == 0) throw new InvalidDataException("Lịch sử trả về chưa đầy đủ.");
            foreach (var trade in received.EnumerateArray())
                trades.Add(System.Text.Json.Nodes.JsonNode.Parse(trade.GetRawText()));
        }
        if (trades.Count != report.TradeTotal) throw new InvalidDataException("Số giao dịch không khớp.");
        result["trades"] = trades;
        result.Remove("trade_total"); result.Remove("trade_offset"); result.Remove("trade_limit");
        return result;
    }

    private void ApplyResult(BacktestResultSnapshot result)
    {
        var metrics = result.Metrics;
        Text("BacktestResultHeaderText").Text =
            $"Kết quả Backtest - {result.Symbol} ({(result.Model.StartsWith("OBSERVED_", StringComparison.Ordinal) ? "Tick" : "M1 OHLC")})  {result.FromDate} - {result.ToDate}";

        Text("NetProfitText").Text = Money(metrics.NetProfit);
        Text("NetProfitText").Foreground = ProfitBrush(metrics.NetProfit);
        Text("NetProfitPctText").Text = Percent(metrics.NetProfitPct);
        Text("NetProfitPctText").Foreground = ProfitBrush(metrics.NetProfit);

        Text("WinRateText").Text = $"{metrics.WinRate:0.00}%";
        Text("WinDetailText").Text = $"{metrics.Wins} / {metrics.Losses} thắng/thua";

        Text("ProfitFactorText").Text = metrics.ProfitFactor.HasValue
            ? metrics.ProfitFactor.Value.ToString("0.00", CultureInfo.InvariantCulture)
            : metrics.GrossProfit > 0 && Math.Abs(metrics.GrossLoss) < 1e-9
                ? "∞"
                : "—";

        Text("DrawdownPctText").Text = $"{metrics.MaxDrawdownPct:0.00}%";
        Text("DrawdownUsdText").Text = Money(metrics.MaxDrawdownUsd);
        Text("TotalTradesText").Text = metrics.TotalTrades.ToString("N0");

        Text("AverageTradeText").Text = Money(metrics.AverageTrade);
        Text("AverageTradeText").Foreground = ProfitBrush(metrics.AverageTrade);
        double avgPct = Math.Abs(metrics.InitialBalance) < 1e-9
            ? 0
            : metrics.AverageTrade / metrics.InitialBalance * 100.0;
        Text("AverageTradePctText").Text = $"{avgPct:0.00}% / lệnh";

        Chart("EquityChart").TimezoneOffsetMinutes = result.TimezoneOffsetMinutes;
        Chart("DrawdownChart").TimezoneOffsetMinutes = result.TimezoneOffsetMinutes;
        Chart("EquityChart").SetEquityData(result.EquityCurve);
        Chart("DrawdownChart").SetDrawdownData(result.DrawdownCurve);

        if (result.EquityCurve.Count > 0)
        {
            double min = result.EquityCurve.Min(item => Math.Min(item.Balance, item.Equity));
            double max = result.EquityCurve.Max(item => Math.Max(item.Balance, item.Equity));
            var last = result.EquityCurve[^1];
            Text("EquityRangeText").Text = $"Range: {min:N2} → {max:N2}";
            Text("EquityLastText").Text = $"Last: {last.Equity:N2}";
        }
        else
        {
            Text("EquityRangeText").Text = "Range: —";
            Text("EquityLastText").Text = "Last: —";
        }

        Text("DrawdownRangeText").Text = $"Max: {metrics.MaxDrawdownPct:0.00}%";
        RenderTrades();
    }

    private void ClearResult()
    {
        Text("BacktestResultHeaderText").Text = "Kết quả Backtest — chưa có run";
        foreach (var name in new[]
        {
            "NetProfitText", "NetProfitPctText", "WinRateText", "WinDetailText",
            "ProfitFactorText", "DrawdownPctText", "DrawdownUsdText",
            "TotalTradesText", "AverageTradeText", "AverageTradePctText"
        })
        {
            Text(name).Text = "—";
        }

        Text("EquityRangeText").Text = "Range: —";
        Text("EquityLastText").Text = "Last: —";
        Text("DrawdownRangeText").Text = "Max: —";
        Chart("EquityChart").Clear();
        Chart("DrawdownChart").Clear();
        RenderTrades();
    }

    private void RenderHistory()
    {
        var host = Panel("BacktestHistoryRowsHost");
        host.Children.Clear();

        if (_history.Count == 0)
        {
            host.Children.Add(EmptyRow("Chưa có kết quả Backtest đã lưu."));
            Text("HistoryCountText").Text = "Tổng: 0 kết quả";
            return;
        }

        for (int index = 0; index < _history.Count; index++)
        {
            var item = _history[index];
            var grid = CreateGrid("0.34*,1.38*,0.72*,0.52*,0.88*,0.88*,1*,0.82*,0.6*,0.74*,0.7*,0.8*");
            AddCell(grid, 0, (index + 1).ToString());
            AddCell(grid, 1, LocalTime(item.CreatedAtUtc));
            AddCell(grid, 2, item.Symbol);
            AddCell(grid, 3, item.Model.StartsWith("OBSERVED_", StringComparison.Ordinal) ? "Tick" : "M1");
            AddCell(grid, 4, item.FromDate);
            AddCell(grid, 5, item.ToDate);
            AddCell(grid, 6, Money(item.Metrics.NetProfit), ProfitBrush(item.Metrics.NetProfit));
            AddCell(grid, 7, $"{item.Metrics.MaxDrawdownPct:0.00}%", Brushes.IndianRed);
            AddCell(
                grid,
                8,
                item.Metrics.ProfitFactor.HasValue
                    ? item.Metrics.ProfitFactor.Value.ToString("0.00", CultureInfo.InvariantCulture)
                    : "—");
            AddCell(grid, 9, $"{item.Metrics.WinRate:0.00}%");
            AddCell(grid, 10, item.Metrics.TotalTrades.ToString());
            AddCell(grid, 11, "Hoàn thành", Brushes.LightGreen);

            var button = new Button
            {
                Tag = item.RunId,
                Classes = { "btRow" },
                Content = grid,
                Background = _selectedHistory?.RunId == item.RunId
                    ? new SolidColorBrush(Color.Parse("#0A3970"))
                    : Brushes.Transparent
            };
            button.Click += HistoryRow_OnClick;
            host.Children.Add(button);
        }

        Text("HistoryCountText").Text = $"Tổng: {_history.Count} kết quả";
    }

    private void RenderTrades()
    {
        var host = Panel("BacktestTradeRowsHost");
        host.Children.Clear();

        if (_current is null || _current.Trades.Count == 0)
        {
            host.Children.Add(EmptyRow("Chưa có giao dịch Backtest để hiển thị."));
            Text("TradePageSummaryText").Text = "Hiển thị 0 / 0 giao dịch";
            Text("TradePageText").Text = "1 / 1";
            Button("PrevTradePageButton").IsEnabled = false;
            Button("NextTradePageButton").IsEnabled = false;
            return;
        }

        foreach (var trade in _current.Trades)
        {
            var grid = CreateGrid("0.34*,1.35*,0.58*,0.52*,0.88*,0.88*,0.82*,0.86*,0.6*");
            AddCell(grid, 0, trade.TradeId.ToString());
            AddCell(grid, 1, Epoch(trade.EntryTime));
            AddCell(grid, 2, trade.Side, SideBrush(trade.Side));
            AddCell(grid, 3, trade.Volume.ToString("0.00"));
            AddCell(grid, 4, trade.EntryPrice.ToString("0.00###"));
            AddCell(grid, 5, trade.ExitPrice.ToString("0.00###"));
            AddCell(grid, 6, Money(trade.NetPl), ProfitBrush(trade.NetPl));
            AddCell(grid, 7, Duration(trade.DurationSeconds));
            AddCell(grid, 8, trade.ExitReason);
            host.Children.Add(RowBorder(grid));
        }

        int pages = Math.Max(1, (int)Math.Ceiling(_current.TradeTotal / (double)TradePageSize));
        int first = _current.TradeOffset + 1;
        int last = _current.TradeOffset + _current.Trades.Count;
        Text("TradePageSummaryText").Text =
            $"Hiển thị {first} - {last} / {_current.TradeTotal} giao dịch";
        Text("TradePageText").Text = $"{_tradePage + 1} / {pages}";
        Button("PrevTradePageButton").IsEnabled = _tradePage > 0;
        Button("NextTradePageButton").IsEnabled = _tradePage + 1 < pages;
    }

    private async Task<bool> ConfirmDeleteAsync(BacktestHistoryItem item)
    {
        var owner = TopLevel.GetTopLevel(this) as Window;
        if (owner is null)
            return false;

        bool accepted = false;
        var dialog = new Window
        {
            Width = 430,
            Height = 220,
            MinWidth = 430,
            MinHeight = 220,
            CanResize = false,
            [LocalizationService.TitleProperty] = "XAUPY • Xóa kết quả Backtest",
            Background = new SolidColorBrush(Color.Parse("#031426"))
        };

        var cancel = new Button { [LocalizationService.TextProperty] = "Hủy", Classes = { "secondary" } };
        var confirm = new Button
        {
            [LocalizationService.TextProperty] = "Xóa kết quả",
            Background = new SolidColorBrush(Color.Parse("#B61C35")),
            Foreground = Brushes.White,
            BorderBrush = Brushes.IndianRed,
            BorderThickness = new Thickness(1),
            CornerRadius = new CornerRadius(5)
        };
        cancel.Click += (_, _) => dialog.Close();
        confirm.Click += (_, _) =>
        {
            accepted = true;
            dialog.Close();
        };

        var buttons = new StackPanel
        {
            Orientation = Orientation.Horizontal,
            HorizontalAlignment = HorizontalAlignment.Right,
            Spacing = 8
        };
        buttons.Children.Add(cancel);
        buttons.Children.Add(confirm);

        var content = new StackPanel
        {
            Margin = new Thickness(18),
            Spacing = 12
        };
        content.Children.Add(
            new TextBlock
            {
                [LocalizationService.TextProperty] = "Xóa kết quả Backtest đã lưu?",
                [AppearanceService.BaseFontSizeProperty] = 20d,
                FontWeight = FontWeight.SemiBold
            });
        content.Children.Add(
            new TextBlock
            {
                Text = $"{item.Symbol} • {item.FromDate} → {item.ToDate} • hash {ShortHash(item.ResultHash)}",
                Foreground = Brushes.LightGray,
                TextWrapping = TextWrapping.Wrap
            });
        content.Children.Add(buttons);
        dialog.Content = content;

        await dialog.ShowDialog(owner);
        return accepted;
    }

    private static Grid CreateGrid(string columns) => new()
    {
        ColumnDefinitions = new ColumnDefinitions(columns),
        MinHeight = 29
    };

    private static void AddCell(
        Grid grid,
        int column,
        string value,
        IBrush? brush = null)
    {
        var text = new TextBlock
        {
            Text = value,
            Foreground = brush ?? new SolidColorBrush(Color.Parse("#D8E5F2")),
            [AppearanceService.BaseFontSizeProperty] = 12d,
            VerticalAlignment = VerticalAlignment.Center,
            Margin = new Thickness(7, 5),
            TextTrimming = TextTrimming.CharacterEllipsis
        };
        Grid.SetColumn(text, column);
        grid.Children.Add(text);
    }

    private static Border RowBorder(Grid grid) => new()
    {
        Background = new SolidColorBrush(Color.Parse("#06192C")),
        BorderBrush = new SolidColorBrush(Color.Parse("#123D5D")),
        BorderThickness = new Thickness(0, 1, 0, 0),
        Child = grid
    };

    private static Border EmptyRow(string message) => new()
    {
        Background = new SolidColorBrush(Color.Parse("#06192C")),
        Padding = new Thickness(12, 14),
        Child = new TextBlock
        {
            Text = message,
            Foreground = new SolidColorBrush(Color.Parse("#8099B2")),
            HorizontalAlignment = HorizontalAlignment.Center,
            TextWrapping = TextWrapping.Wrap
        }
    };

    private void SetStatus(string message, IBrush brush)
    {
        Text("BacktestRunStatusText").Text = message;
        Text("BacktestRunStatusText").Foreground = brush;
    }

    private static string Money(double value) =>
        $"{value:+0.00;-0.00;0.00} USD";

    private static string Percent(double value) =>
        $"{value:+0.00;-0.00;0.00}%";

    private static IBrush ProfitBrush(double value) =>
        value > 0
            ? Brushes.LightGreen
            : value < 0
                ? Brushes.IndianRed
                : Brushes.LightGray;

    private static IBrush SideBrush(string side) =>
        side.Equals("BUY", StringComparison.OrdinalIgnoreCase)
            ? Brushes.DeepSkyBlue
            : side.Equals("SELL", StringComparison.OrdinalIgnoreCase)
                ? Brushes.IndianRed
                : Brushes.LightGray;

    private string Epoch(long value)
    {
        try
        {
            return DateTimeOffset
                .FromUnixTimeSeconds(value)
                .AddMinutes(_current?.TimezoneOffsetMinutes ?? 0)
                .ToString("yyyy.MM.dd HH:mm");
        }
        catch (ArgumentOutOfRangeException)
        {
            return value.ToString();
        }
    }

    private static string LocalTime(string raw)
    {
        return DateTimeOffset.TryParse(raw, out var value)
            ? value.ToLocalTime().ToString("yyyy.MM.dd HH:mm")
            : raw;
    }

    private static string Duration(long seconds)
    {
        var span = TimeSpan.FromSeconds(Math.Max(0, seconds));
        if (span.TotalDays >= 1)
            return $"{(int)span.TotalDays}d {span.Hours}h";
        if (span.TotalHours >= 1)
            return $"{(int)span.TotalHours}h {span.Minutes}m";
        return $"{span.Minutes}m {span.Seconds}s";
    }

    private static bool TryNumber(string? text, out double value)
    {
        if (double.TryParse(text, NumberStyles.Float, CultureInfo.InvariantCulture, out value))
            return true;
        return double.TryParse(text, NumberStyles.Float, CultureInfo.CurrentCulture, out value);
    }

    private static string ShortHash(string value) =>
        string.IsNullOrWhiteSpace(value)
            ? "—"
            : value[..Math.Min(10, value.Length)];

    private static string Csv(string value) =>
        "\"" + value.Replace("\"", "\"\"") + "\"";

    private static string Invariant(double value) =>
        value.ToString("0.########", CultureInfo.InvariantCulture);

    private TextBlock Text(string name) =>
        this.FindControl<TextBlock>(name)
        ?? throw new InvalidOperationException($"Missing Backtest TextBlock: {name}");

    private TextBox Box(string name) =>
        this.FindControl<TextBox>(name)
        ?? throw new InvalidOperationException($"Missing Backtest TextBox: {name}");

    private Button Button(string name) =>
        this.FindControl<Button>(name)
        ?? throw new InvalidOperationException($"Missing Backtest Button: {name}");

    private StackPanel Panel(string name) =>
        this.FindControl<StackPanel>(name)
        ?? throw new InvalidOperationException($"Missing Backtest panel: {name}");

    private BacktestChartControl Chart(string name) =>
        this.FindControl<BacktestChartControl>(name)
        ?? throw new InvalidOperationException($"Missing Backtest chart: {name}");
}
