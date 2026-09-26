using System.Globalization;
using System.Text;
using System.Text.Json;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Platform.Storage;
using Avalonia.Threading;
using XAUPY.Ipc;

namespace XAUPY.Desktop;

public partial class OptimizerDashboard : UserControl
{
    private static readonly string[] Timeframes =
    {
        "M1", "M3", "M5", "M15", "M30", "H1", "H2", "H4"
    };

    private static readonly FilePickerFileType HistoricalDataType = new("XAUPY Historical Data")
    {
        Patterns = new[] { "*.json", "*.csv" }
    };

    private static readonly FilePickerFileType OptimizerPresetType = new("XAUPY Optimizer Preset")
    {
        Patterns = new[] { "*.json" }
    };

    private readonly DispatcherTimer _pollTimer;
    private EngineProcessSupervisor? _supervisor;
    private BacktestDatasetInfo? _dataset;
    private JsonElement? _activeProfile;
    private OptimizerStatusSnapshot _status = OptimizerStatusSnapshot.Idle;
    private OptimizerResultSnapshot? _currentSweep;
    private OptimizerResultSnapshot? _currentWalkForward;
    private bool _initialized;
    private bool _loading;
    private bool _suppressInputEvents;
    private string? _slPath;
    private string? _tpPath;
    private bool _includeRsiRows;
    private string? _triggerDeltaPath;
    private bool _includeMaPeriod;

    private sealed record AxisOption(string Label, string Path)
    {
        public override string ToString() => Label;
    }

    public OptimizerDashboard()
    {
        InitializeComponent();

        foreach (var name in new[]
        {
            "DirectionTfMinCombo", "DirectionTfMaxCombo",
            "PullbackTfMinCombo", "PullbackTfMaxCombo",
            "TriggerTfMinCombo", "TriggerTfMaxCombo"
        })
        {
            Combo(name).ItemsSource = Timeframes;
        }

        _pollTimer = new DispatcherTimer
        {
            Interval = TimeSpan.FromSeconds(1)
        };
        _pollTimer.Tick += async (_, _) =>
        {
            if (!IsVisible || _supervisor is null || _loading)
                return;
            if (_supervisor.State != EngineConnectionState.Ready)
                return;
            if (!_status.IsActive)
                return;

            try
            {
                var current = await _supervisor.QueryOptimizerStatusAsync(_status.JobId);
                ApplyStatus(current);
            }
            catch
            {
                // Heartbeat path remains authoritative; transient polling failure
                // must not manufacture a state transition.
            }
        };
        _pollTimer.Start();

        RenderStatus();
        RenderTopSetups();
        RenderWalkForward();
        ClearHeatmap("Chưa có kết quả Sweep.");
        _initialized = true;
    }

    public void AttachSupervisor(EngineProcessSupervisor supervisor)
    {
        _supervisor = supervisor;
    }

    public void ApplyEngineState(EngineConnectionState state)
    {
        bool ready = state == EngineConnectionState.Ready;
        Text("EngineResourceText").Text = ready ? "OK" : state.ToString().ToUpperInvariant();
        Text("EngineResourceText").Foreground = ready ? Brushes.LightGreen : Brushes.Gold;
        Text("BacktestResourceText").Text = ready ? "READY" : "WAIT";
        Text("BacktestResourceText").Foreground = ready ? Brushes.LightGreen : Brushes.Gold;
    }

    public void ApplyStatus(OptimizerStatusSnapshot status)
    {
        _status = status;
        RenderStatus();

        if (status.Status == "COMPLETED" &&
            !string.IsNullOrWhiteSpace(status.ResultRunId) &&
            !IsResultLoaded(status.ResultRunId!))
        {
            _ = LoadCompletedResultAsync(status.ResultRunId!);
        }
    }

    public async Task EnsureLoadedAsync(bool force = false)
    {
        if (_loading || _supervisor is null)
            return;

        if (_supervisor.State != EngineConnectionState.Ready)
        {
            SetStateMessage("Đang chờ Python Engine READY...", Brushes.Gold);
            return;
        }

        string? terminalRunId = null;
        string? latestSweepRunId = null;
        string? latestWalkForwardRunId = null;

        try
        {
            _loading = true;

            if (force || _activeProfile is null)
            {
                _activeProfile = await _supervisor.GetActiveConfigAsync();
                InitializeRangesFromActiveProfile(_activeProfile.Value);
            }

            var status = await _supervisor.QueryOptimizerStatusAsync();
            _status = status;
            RenderStatus();

            if (!status.IsActive)
            {
                if (status.Status == "COMPLETED" &&
                    !string.IsNullOrWhiteSpace(status.ResultRunId) &&
                    !IsResultLoaded(status.ResultRunId!))
                {
                    terminalRunId = status.ResultRunId;
                }

                if (_currentSweep is null || _currentWalkForward is null)
                {
                    var history = await _supervisor.QueryOptimizerHistoryAsync(50);
                    if (history.Ok)
                    {
                        if (_currentSweep is null)
                        {
                            latestSweepRunId = history.Items
                                .FirstOrDefault(item =>
                                    string.Equals(
                                        item.Mode,
                                        "SWEEP",
                                        StringComparison.Ordinal))
                                ?.RunId;
                        }

                        if (_currentWalkForward is null)
                        {
                            latestWalkForwardRunId = history.Items
                                .FirstOrDefault(item =>
                                    string.Equals(
                                        item.Mode,
                                        "WALK_FORWARD",
                                        StringComparison.Ordinal))
                                ?.RunId;
                        }
                    }
                }
            }
        }
        catch (Exception ex)
        {
            SetStateMessage($"Optimizer load lỗi: {ex.Message}", Brushes.IndianRed);
        }
        finally
        {
            _loading = false;
        }

        if (!string.IsNullOrWhiteSpace(terminalRunId))
            await LoadCompletedResultAsync(terminalRunId!);

        if (!string.IsNullOrWhiteSpace(latestSweepRunId) &&
            !IsResultLoaded(latestSweepRunId!))
        {
            await LoadCompletedResultAsync(latestSweepRunId!);
        }

        if (!string.IsNullOrWhiteSpace(latestWalkForwardRunId) &&
            !IsResultLoaded(latestWalkForwardRunId!))
        {
            await LoadCompletedResultAsync(latestWalkForwardRunId!);
        }
    }

    private void InitializeRangesFromActiveProfile(JsonElement profile)
    {
        _suppressInputEvents = true;
        try
        {
            string direction = GetString(profile, "timeframes", "direction") ?? "M30";
            string pullback = GetString(profile, "timeframes", "pullback") ?? "M5";
            string trigger = GetString(profile, "timeframes", "trigger") ?? "M1";

            SetTimeframeRange(
                "DirectionTfMinCombo",
                "DirectionTfMaxCombo",
                direction,
                lowerOffset: 0,
                upperOffset: 1);
            SetTimeframeRange(
                "PullbackTfMinCombo",
                "PullbackTfMaxCombo",
                pullback,
                lowerOffset: -1,
                upperOffset: 1);
            SetTimeframeRange(
                "TriggerTfMinCombo",
                "TriggerTfMaxCombo",
                trigger,
                lowerOffset: 0,
                upperOffset: 1);

            Text("DirectionTfDefaultText").Text = direction;
            Text("PullbackTfDefaultText").Text = pullback;
            Text("TriggerTfDefaultText").Text = trigger;

            _includeRsiRows = GetBool(profile, "pullback", "rsi_enabled") ?? false;
            double rsiBuy = GetDouble(profile, "pullback", "rsi_buy_level") ?? 40;
            double rsiSell = GetDouble(profile, "pullback", "rsi_sell_level") ?? 60;
            SetNumericRange(
                "RsiBuyMinBox", "RsiBuyMaxBox", "RsiBuyStepBox",
                Math.Max(0, rsiBuy - 5), Math.Min(100, rsiBuy + 5), 5);
            SetNumericRange(
                "RsiSellMinBox", "RsiSellMaxBox", "RsiSellStepBox",
                Math.Max(0, rsiSell - 5), Math.Min(100, rsiSell + 5), 5);
            Text("RsiBuyDefaultText").Text = Format(rsiBuy);
            Text("RsiSellDefaultText").Text = Format(rsiSell);
            SetRowEnabled(
                _includeRsiRows,
                "RsiBuyMinBox", "RsiBuyMaxBox", "RsiBuyStepBox",
                "RsiSellMinBox", "RsiSellMaxBox", "RsiSellStepBox");

            bool triggerRsi = GetBool(profile, "trigger", "rsi_enabled") ?? false;
            bool triggerZ = GetBool(profile, "trigger", "z_enabled") ?? false;
            if (triggerRsi)
            {
                _triggerDeltaPath = "trigger.rsi_reversal_delta";
                Text("TriggerDeltaParameterLabel").Text = "RSI Δ Trigger";
                double value = GetDouble(profile, "trigger", "rsi_reversal_delta") ?? 3;
                SetNumericRange(
                    "RsiDeltaMinBox", "RsiDeltaMaxBox", "RsiDeltaStepBox",
                    value, value, 1);
                Text("RsiDeltaDefaultText").Text = Format(value);
                SetRowEnabled(true, "RsiDeltaMinBox", "RsiDeltaMaxBox", "RsiDeltaStepBox");
            }
            else if (triggerZ)
            {
                _triggerDeltaPath = "trigger.z_reversal_delta";
                Text("TriggerDeltaParameterLabel").Text = "Z-Score / Delta";
                double value = GetDouble(profile, "trigger", "z_reversal_delta") ?? 0.5;
                SetNumericRange(
                    "RsiDeltaMinBox", "RsiDeltaMaxBox", "RsiDeltaStepBox",
                    value, value, 0.25);
                Text("RsiDeltaDefaultText").Text = Format(value);
                SetRowEnabled(true, "RsiDeltaMinBox", "RsiDeltaMaxBox", "RsiDeltaStepBox");
            }
            else
            {
                _triggerDeltaPath = null;
                Text("TriggerDeltaParameterLabel").Text = "Trigger Delta (disabled)";
                Text("RsiDeltaDefaultText").Text = "—";
                SetRowEnabled(false, "RsiDeltaMinBox", "RsiDeltaMaxBox", "RsiDeltaStepBox");
            }

            _includeMaPeriod = GetBool(profile, "direction", "ma_enabled") ?? false;
            string maType = GetString(profile, "direction", "ma_type") ?? "EMA";
            Text("MaParameterLabel").Text = $"{maType} Period";
            double ma = GetDouble(profile, "direction", "ma_period") ?? 50;
            SetNumericRange(
                "EmaMinBox", "EmaMaxBox", "EmaStepBox",
                ma, ma, 20);
            Text("EmaDefaultText").Text = Format(ma);
            SetRowEnabled(_includeMaPeriod, "EmaMinBox", "EmaMaxBox", "EmaStepBox");

            string slMode = GetString(profile, "stop_loss", "mode") ?? "STRUCTURE";
            if (slMode == "STRUCTURE")
            {
                _slPath = "stop_loss.structure_lookback";
                Text("SlParameterLabel").Text = "SL Structure Lookback";
                double value = GetDouble(profile, "stop_loss", "structure_lookback") ?? 3;
                SetNumericRange(
                    "SlMinBox", "SlMaxBox", "SlStepBox",
                    value, value, 1);
                Text("SlDefaultText").Text = Format(value);
                SetRowEnabled(true, "SlMinBox", "SlMaxBox", "SlStepBox");
            }
            else if (slMode == "FIXED")
            {
                _slPath = "stop_loss.fixed_price_units";
                Text("SlParameterLabel").Text = "SL Fixed";
                double value = GetDouble(profile, "stop_loss", "fixed_price_units") ?? 5;
                SetNumericRange(
                    "SlMinBox", "SlMaxBox", "SlStepBox",
                    value, value, 2);
                Text("SlDefaultText").Text = Format(value);
                SetRowEnabled(true, "SlMinBox", "SlMaxBox", "SlStepBox");
            }
            else
            {
                _slPath = null;
                Text("SlParameterLabel").Text = $"SL {slMode} (Task 011 chưa hỗ trợ)";
                Text("SlDefaultText").Text = "—";
                SetRowEnabled(false, "SlMinBox", "SlMaxBox", "SlStepBox");
            }

            string tpMode = GetString(profile, "take_profit", "mode") ?? "FIXED";
            if (tpMode == "FIXED")
            {
                _tpPath = "take_profit.fixed_price_units";
                Text("TpParameterLabel").Text = "TP Fixed";
                double value = GetDouble(profile, "take_profit", "fixed_price_units") ?? 7;
                SetNumericRange(
                    "TpMinBox", "TpMaxBox", "TpStepBox",
                    value, value, 2);
                Text("TpDefaultText").Text = Format(value);
                SetRowEnabled(true, "TpMinBox", "TpMaxBox", "TpStepBox");
            }
            else if (tpMode == "RR")
            {
                _tpPath = "take_profit.rr_ratio";
                Text("TpParameterLabel").Text = "TP RR Ratio";
                double value = GetDouble(profile, "take_profit", "rr_ratio") ?? 1.5;
                SetNumericRange(
                    "TpMinBox", "TpMaxBox", "TpStepBox",
                    value, value, 0.5);
                Text("TpDefaultText").Text = Format(value);
                SetRowEnabled(true, "TpMinBox", "TpMaxBox", "TpStepBox");
            }
            else
            {
                _tpPath = null;
                Text("TpParameterLabel").Text = $"TP {tpMode} (Task 011 chưa hỗ trợ)";
                Text("TpDefaultText").Text = "—";
                SetRowEnabled(false, "TpMinBox", "TpMaxBox", "TpStepBox");
            }

            Box("WorkersBox").Text = Math.Max(
                1,
                Math.Min(4, Environment.ProcessorCount)).ToString(CultureInfo.InvariantCulture);

            UpdateCombinationPreview();
        }
        finally
        {
            _suppressInputEvents = false;
        }
    }

    private async void SelectDataset_OnClick(object? sender, RoutedEventArgs e)
    {
        await SelectDatasetAsync();
    }

    private async Task<bool> SelectDatasetAsync()
    {
        if (_supervisor is null || _supervisor.State != EngineConnectionState.Ready)
        {
            SetStateMessage("Python Engine chưa READY.", Brushes.Gold);
            return false;
        }

        var storage = TopLevel.GetTopLevel(this)?.StorageProvider;
        if (storage is null || !storage.CanOpen)
        {
            SetStateMessage("Storage provider không hỗ trợ mở file.", Brushes.IndianRed);
            return false;
        }

        var files = await storage.OpenFilePickerAsync(
            new FilePickerOpenOptions
            {
                Title = "Chọn dữ liệu lịch sử M1 cho Optimizer",
                AllowMultiple = false,
                FileTypeFilter = new[] { HistoricalDataType }
            });

        var file = files.FirstOrDefault();
        if (file is null)
            return false;

        try
        {
            var info = await _supervisor.InspectBacktestDatasetAsync(file.Path.LocalPath);
            _dataset = info;
            Box("OptimizeFromDateBox").Text = info.FirstDate;
            Box("OptimizeToDateBox").Text = info.LastDate;
            Text("OptimizerDatasetText").Text =
                $"Dataset: {info.FileName} • {info.BarCount:N0} M1 • SHA {ShortHash(info.DatasetFingerprint)}";
            Text("DatasetResourceText").Text = "OK";
            Text("DatasetResourceText").Foreground = Brushes.LightGreen;
            SetStateMessage("Dataset hợp lệ. Sẵn sàng tối ưu.", Brushes.LightGreen);
            return true;
        }
        catch (Exception ex)
        {
            _dataset = null;
            Text("OptimizerDatasetText").Text = "Dataset: chưa chọn";
            Text("DatasetResourceText").Text = "WAIT";
            Text("DatasetResourceText").Foreground = Brushes.Gold;
            SetStateMessage($"Dataset bị từ chối: {ex.Message}", Brushes.IndianRed);
            return false;
        }
    }

    private async void StartOptimizer_OnClick(object? sender, RoutedEventArgs e)
    {
        await StartJobAsync(walkForward: false);
    }

    private async void RunWalkForward_OnClick(object? sender, RoutedEventArgs e)
    {
        await StartJobAsync(walkForward: true);
    }

    private async Task StartJobAsync(bool walkForward)
    {
        if (_supervisor is null || _supervisor.State != EngineConnectionState.Ready)
        {
            SetStateMessage("Python Engine chưa READY.", Brushes.Gold);
            return;
        }
        if (_status.IsActive)
        {
            SetStateMessage("Đã có một optimizer job đang chạy.", Brushes.Gold);
            return;
        }
        if (_dataset is null && !await SelectDatasetAsync())
            return;

        try
        {
            var ranges = BuildParameterRanges();
            var rangeJson = JsonSerializer.SerializeToElement(ranges);
            if (!TryContextValues(
                    out var fromDate,
                    out var toDate,
                    out var balance,
                    out var spread,
                    out var commission,
                    out var minTrades,
                    out var workers))
            {
                return;
            }

            OptimizerStatusSnapshot status;
            if (walkForward)
            {
                if (!int.TryParse(
                        Box("WalkForwardFoldsBox").Text,
                        NumberStyles.Integer,
                        CultureInfo.InvariantCulture,
                        out int folds))
                {
                    SetStateMessage("Folds không hợp lệ.", Brushes.IndianRed);
                    return;
                }

                double ratio = CurrentTrainRatio();
                bool rolling = CurrentRolling();
                status = await _supervisor.StartWalkForwardAsync(
                    _dataset!.Path,
                    fromDate,
                    toDate,
                    balance,
                    spread,
                    commission,
                    minTrades,
                    workers,
                    rangeJson,
                    folds,
                    ratio,
                    rolling);
            }
            else
            {
                status = await _supervisor.StartOptimizerAsync(
                    _dataset!.Path,
                    fromDate,
                    toDate,
                    balance,
                    spread,
                    commission,
                    minTrades,
                    workers,
                    rangeJson);
            }

            ApplyStatus(status);
        }
        catch (Exception ex)
        {
            SetStateMessage(
                $"{(walkForward ? "Walk-Forward" : "Optimizer")} không khởi động: {ex.Message}",
                Brushes.IndianRed);
        }
    }

    private async void StopOptimizer_OnClick(object? sender, RoutedEventArgs e)
    {
        if (_supervisor is null || string.IsNullOrWhiteSpace(_status.JobId))
            return;

        try
        {
            var status = await _supervisor.CancelOptimizerAsync(_status.JobId);
            ApplyStatus(status);
        }
        catch (Exception ex)
        {
            SetStateMessage($"Không dừng được optimizer: {ex.Message}", Brushes.IndianRed);
        }
    }

    private async Task LoadCompletedResultAsync(string runId)
    {
        if (_supervisor is null || _loading || IsResultLoaded(runId))
            return;

        try
        {
            _loading = true;
            var result = await _supervisor.GetOptimizerResultAsync(
                runId,
                candidateOffset: 0,
                candidateLimit: 10);

            if (result.Mode == "SWEEP")
            {
                _currentSweep = result;
                RenderTopSetups();
                ConfigureHeatmapAxes(result);
                await RefreshHeatmapAsync();
            }
            else if (result.Mode == "WALK_FORWARD")
            {
                _currentWalkForward = result;
                RenderWalkForward();
            }

            SetStateMessage(
                $"{result.Mode} hoàn thành • hash {ShortHash(result.OptimizerHash)}",
                Brushes.LightGreen);
        }
        catch (Exception ex)
        {
            SetStateMessage($"Không tải được optimizer result: {ex.Message}", Brushes.IndianRed);
        }
        finally
        {
            _loading = false;
        }
    }

    private bool IsResultLoaded(string runId)
    {
        return string.Equals(
                   _currentSweep?.RunId,
                   runId,
                   StringComparison.Ordinal)
               || string.Equals(
                   _currentWalkForward?.RunId,
                   runId,
                   StringComparison.Ordinal);
    }

    private void RenderStatus()
    {
        var status = _status.Status;
        string label = status switch
        {
            "RUNNING" => "ĐANG CHẠY TỐI ƯU...",
            "QUEUED" => "ĐANG XẾP HÀNG...",
            "STOPPING" => "ĐANG DỪNG...",
            "COMPLETED" => "HOÀN THÀNH",
            "CANCELLED" => "ĐÃ HỦY",
            "FAILED" => "LỖI",
            _ => "CHƯA CHẠY"
        };
        IBrush color = status switch
        {
            "RUNNING" or "COMPLETED" => Brushes.LightGreen,
            "FAILED" => Brushes.IndianRed,
            "QUEUED" or "STOPPING" or "CANCELLED" => Brushes.Gold,
            _ => Brushes.Gold
        };

        Text("OptimizerStateText").Text = label;
        Text("OptimizerStateText").Foreground = color;
        Text("OptimizerPhaseText").Text =
            status == "FAILED" && !string.IsNullOrWhiteSpace(_status.Error)
                ? _status.Error!
                : PhaseLabel(_status);
        Text("OptimizerElapsedText").Text = FormatDuration(_status.ElapsedSeconds);

        Progress("OptimizerProgressBar").Value = Math.Clamp(_status.ProgressPct, 0, 100);
        Text("OptimizerProgressText").Text = $"{_status.ProgressPct:0.0}%";
        Text("TotalWorkLabelText").Text =
            string.Equals(_status.Mode, "WALK_FORWARD", StringComparison.Ordinal)
                ? "Tổng công việc"
                : "Tổng tổ hợp";
        Text("TotalWorkText").Text = _status.TotalWork.ToString("N0");
        Text("CompletedWorkText").Text = _status.CompletedWork.ToString("N0");
        Text("InFlightText").Text = _status.InFlight.ToString("N0");
        Text("RemainingWorkText").Text =
            Math.Max(0, _status.TotalWork - _status.CompletedWork).ToString("N0");
        Text("OptimizerSpeedText").Text = $"{_status.SpeedPerMinute:0.0}/phút";
        Text("OptimizerEtaText").Text =
            _status.EtaSeconds.HasValue
                ? FormatDuration(_status.EtaSeconds.Value)
                : "—";

        int activeWorkerSlots = _status.Workers <= 0
            ? 0
            : Math.Min(_status.InFlight, _status.Workers);
        double utilization = _status.Workers <= 0
            ? 0
            : activeWorkerSlots / (double)_status.Workers * 100.0;
        Progress("WorkerProgressBar").Value = utilization;
        Text("WorkerUtilizationText").Text =
            _status.Workers > 0
                ? $"{activeWorkerSlots}/{_status.Workers}"
                : "0/0";
        Text("ThroughputText").Text =
            _status.SpeedPerMinute > 0
                ? $"{_status.SpeedPerMinute:0}"
                : "—";

        Button("StartOptimizerButton").IsEnabled = !_status.IsActive;
        Button("RunWalkForwardButton").IsEnabled = !_status.IsActive;
        Button("StopOptimizerButton").IsEnabled = _status.IsActive;

        Text("WriterResourceText").Text = status switch
        {
            "COMPLETED" => "SAVED",
            "FAILED" => "ERROR",
            _ => "READY"
        };
        Text("WriterResourceText").Foreground =
            status == "FAILED" ? Brushes.IndianRed : Brushes.LightGreen;
    }

    private void RenderTopSetups()
    {
        var host = Panel("TopSetupRowsHost");
        host.Children.Clear();

        if (_currentSweep is null || _currentSweep.Candidates.Count == 0)
        {
            host.Children.Add(EmptyRow("Chưa có kết quả Parameter Sweep."));
            return;
        }

        foreach (var candidate in _currentSweep.Candidates
                     .Where(item => item.Eligible)
                     .OrderBy(item => item.Rank ?? int.MaxValue)
                     .Take(10))
        {
            var grid = new Grid
            {
                ColumnDefinitions = new ColumnDefinitions("34,62,92,68,70,72,*,62"),
                MinHeight = 32
            };

            AddCell(grid, 0, (candidate.Rank ?? 0).ToString());
            AddCell(grid, 1, candidate.Score?.ToString("0.00") ?? "—");
            AddCell(
                grid,
                2,
                Money(candidate.Metrics.NetProfit),
                ProfitBrush(candidate.Metrics.NetProfit));
            AddCell(grid, 3, candidate.TradeSharpe.ToString("0.00"));
            AddCell(grid, 4, $"{candidate.Metrics.MaxDrawdownPct:0.0}%", Brushes.IndianRed);
            AddCell(grid, 5, $"{candidate.Metrics.WinRate:0.0}%");
            AddCell(grid, 6, ParameterSummary(candidate.Parameters));

            var action = new Button
            {
                Content = "Xem",
                Tag = candidate,
                Classes = { "secondary" },
                Padding = new Thickness(8, 3),
                FontSize = 10,
                HorizontalAlignment = HorizontalAlignment.Center
            };
            action.Click += ViewCandidate_OnClick;
            Grid.SetColumn(action, 7);
            grid.Children.Add(action);
            host.Children.Add(RowBorder(grid));
        }
    }

    private async void ViewCandidate_OnClick(object? sender, RoutedEventArgs e)
    {
        if (sender is not Button { Tag: OptimizerCandidateSnapshot candidate })
            return;

        var owner = TopLevel.GetTopLevel(this) as Window;
        if (owner is null)
            return;

        string body = JsonSerializer.Serialize(
            new
            {
                rank = candidate.Rank,
                score = candidate.Score,
                trade_sharpe = candidate.TradeSharpe,
                parameters = candidate.Parameters,
                metrics = candidate.Metrics,
                result_hash = candidate.ResultHash
            },
            new JsonSerializerOptions { WriteIndented = true });

        var dialog = new Window
        {
            Width = 650,
            Height = 560,
            MinWidth = 650,
            MinHeight = 560,
            Title = $"XAUPY • Optimizer candidate #{candidate.Rank}",
            Background = new SolidColorBrush(Color.Parse("#031426")),
            Content = new ScrollViewer
            {
                Content = new TextBlock
                {
                    Text = body,
                    FontFamily = "Consolas",
                    FontSize = 12,
                    TextWrapping = TextWrapping.Wrap,
                    Margin = new Thickness(16)
                }
            }
        };
        await dialog.ShowDialog(owner);
    }

    private void ConfigureHeatmapAxes(OptimizerResultSnapshot result)
    {
        var options = result.ParameterRanges
            .Select(item => new AxisOption(ShortParameterLabel(item.Path), item.Path))
            .ToList();

        Combo("HeatmapXCombo").ItemsSource = options;
        Combo("HeatmapYCombo").ItemsSource = options;

        int x = options.FindIndex(item => item.Path == "pullback.rsi_buy_level");
        int y = options.FindIndex(item => item.Path == "pullback.rsi_sell_level");
        Combo("HeatmapXCombo").SelectedIndex = x >= 0 ? x : 0;
        Combo("HeatmapYCombo").SelectedIndex = y >= 0 ? y : Math.Min(1, options.Count - 1);
    }

    private async void HeatmapSelection_OnChanged(object? sender, SelectionChangedEventArgs e)
    {
        if (!_initialized || _suppressInputEvents)
            return;
        await RefreshHeatmapAsync();
    }

    private async Task RefreshHeatmapAsync()
    {
        if (_supervisor is null ||
            _currentSweep is null ||
            string.IsNullOrWhiteSpace(_currentSweep.RunId))
        {
            return;
        }

        if (Combo("HeatmapXCombo").SelectedItem is not AxisOption x ||
            Combo("HeatmapYCombo").SelectedItem is not AxisOption y ||
            x.Path == y.Path)
        {
            ClearHeatmap("Chọn hai tham số khác nhau.");
            return;
        }

        string metric = CurrentHeatmapMetric();
        try
        {
            var heatmap = await _supervisor.GetOptimizerHeatmapAsync(
                _currentSweep.RunId,
                x.Path,
                y.Path,
                metric);
            RenderHeatmap(heatmap);
        }
        catch (Exception ex)
        {
            ClearHeatmap($"Heatmap lỗi: {ex.Message}");
        }
    }

    private void RenderHeatmap(OptimizerHeatmapSnapshot heatmap)
    {
        var grid = GridControl("HeatmapGridHost");
        grid.Children.Clear();
        grid.ColumnDefinitions.Clear();
        grid.RowDefinitions.Clear();

        int columns = heatmap.XValues.Count + 1;
        int rows = heatmap.YValues.Count + 1;
        for (int i = 0; i < columns; i++)
            grid.ColumnDefinitions.Add(new ColumnDefinition(new GridLength(i == 0 ? 72 : 42)));
        for (int i = 0; i < rows; i++)
            grid.RowDefinitions.Add(new RowDefinition(new GridLength(i == 0 ? 28 : 30)));

        AddHeatmapLabel(grid, 0, 0, "Y \\ X");
        for (int i = 0; i < heatmap.XValues.Count; i++)
            AddHeatmapLabel(grid, i + 1, 0, JsonValueText(heatmap.XValues[i]));
        for (int i = 0; i < heatmap.YValues.Count; i++)
            AddHeatmapLabel(grid, 0, i + 1, JsonValueText(heatmap.YValues[i]));

        double min = heatmap.MinValue ?? 0;
        double max = heatmap.MaxValue ?? 0;
        Text("HeatmapMaxText").Text = heatmap.MaxValue.HasValue
            ? Compact(heatmap.MaxValue.Value)
            : "—";
        Text("HeatmapMinText").Text = heatmap.MinValue.HasValue
            ? Compact(heatmap.MinValue.Value)
            : "—";
        Text("HeatmapMidText").Text =
            heatmap.MinValue.HasValue && heatmap.MaxValue.HasValue &&
            heatmap.MinValue.Value <= 0 && heatmap.MaxValue.Value >= 0
                ? "0"
                : Compact((min + max) / 2.0);

        foreach (var cell in heatmap.Cells)
        {
            int xIndex = FindJsonValueIndex(heatmap.XValues, cell.X);
            int yIndex = FindJsonValueIndex(heatmap.YValues, cell.Y);
            if (xIndex < 0 || yIndex < 0)
                continue;

            var border = new Border
            {
                Margin = new Thickness(1),
                CornerRadius = new CornerRadius(2),
                Background = cell.Value.HasValue
                    ? HeatColor(
                        cell.Value.Value,
                        min,
                        max,
                        heatmap.HigherIsBetter)
                    : new SolidColorBrush(Color.Parse("#12263B")),
                Child = new TextBlock
                {
                    Text = cell.Value.HasValue ? Compact(cell.Value.Value) : "—",
                    FontSize = 9,
                    HorizontalAlignment = HorizontalAlignment.Center,
                    VerticalAlignment = VerticalAlignment.Center,
                    Foreground = Brushes.White
                }
            };
            ToolTip.SetTip(
                border,
                $"{heatmap.XPath}={JsonValueText(cell.X)} • {heatmap.YPath}={JsonValueText(cell.Y)}\n" +
                $"{heatmap.Metric}: {(cell.Value.HasValue ? cell.Value.Value.ToString("0.########") : "—")} • samples={cell.Samples}");
            Grid.SetColumn(border, xIndex + 1);
            Grid.SetRow(border, yIndex + 1);
            grid.Children.Add(border);
        }
    }

    private void ClearHeatmap(string message)
    {
        Text("HeatmapMaxText").Text = "—";
        Text("HeatmapMidText").Text = "—";
        Text("HeatmapMinText").Text = "—";
        var grid = GridControl("HeatmapGridHost");
        grid.Children.Clear();
        grid.ColumnDefinitions.Clear();
        grid.RowDefinitions.Clear();
        grid.Children.Add(
            new TextBlock
            {
                Text = message,
                Foreground = new SolidColorBrush(Color.Parse("#8099B2")),
                Margin = new Thickness(12),
                TextWrapping = TextWrapping.Wrap
            });
    }

    private void RenderWalkForward()
    {
        if (_currentWalkForward?.Aggregate is not { } aggregate)
        {
            foreach (var name in new[]
            {
                "WfAverageProfitText", "WfAverageSharpeText",
                "WfAverageWinrateText", "WfAverageDdText",
                "WfPositiveFoldsText", "WfStabilityText"
            })
            {
                Text(name).Text = "—";
            }
            Text("WfLeakageText").Text = "Chưa có Walk-Forward result.";
            Panel("WalkForwardFoldHost").Children.Clear();
            return;
        }

        Text("WfAverageProfitText").Text = Money(aggregate.AverageNetProfit);
        Text("WfAverageProfitText").Foreground = ProfitBrush(aggregate.AverageNetProfit);
        Text("WfAverageSharpeText").Text = aggregate.AverageTradeSharpe.ToString("0.00");
        Text("WfAverageWinrateText").Text = $"{aggregate.AverageWinRate:0.00}%";
        Text("WfAverageDdText").Text = $"{aggregate.AverageMaxDrawdownPct:0.00}%";
        Text("WfPositiveFoldsText").Text = $"{aggregate.PositiveFoldRatio * 100.0:0.0}%";
        Text("WfStabilityText").Text = aggregate.Stability.ToString("0.00");
        Text("WfLeakageText").Text =
            _currentWalkForward.LeakageGuardPassed
                ? "✓ TRAIN_ONLY • train/test không overlap • out-of-sample validation"
                : "⚠ Leakage guard không PASS.";
        Text("WfLeakageText").Foreground =
            _currentWalkForward.LeakageGuardPassed
                ? Brushes.LightGreen
                : Brushes.IndianRed;

        var host = Panel("WalkForwardFoldHost");
        host.Children.Clear();
        foreach (var fold in _currentWalkForward.Folds)
        {
            host.Children.Add(
                new TextBlock
                {
                    Text =
                        $"F{fold.Fold}: Train {fold.TrainFrom}→{fold.TrainTo} • " +
                        $"Test {fold.TestFrom}→{fold.TestTo} • " +
                        $"OOS P/L {fold.TestMetrics.NetProfit:+0.00;-0.00;0.00}",
                    FontSize = 9.5,
                    Foreground = fold.LeakageGuardPassed
                        ? Brushes.LightGray
                        : Brushes.IndianRed,
                    TextWrapping = TextWrapping.Wrap
                });
        }
    }

    private async void SavePreset_OnClick(object? sender, RoutedEventArgs e)
    {
        var storage = TopLevel.GetTopLevel(this)?.StorageProvider;
        if (storage is null || !storage.CanSave)
            return;

        try
        {
            var ranges = BuildParameterRanges();
            var file = await storage.SaveFilePickerAsync(
                new FilePickerSaveOptions
                {
                    Title = "Lưu Optimizer preset",
                    SuggestedFileName = "XAUPY-Optimizer-Custom.json",
                    DefaultExtension = "json",
                    FileTypeChoices = new[] { OptimizerPresetType }
                });
            if (file is null)
                return;

            var payload = new
            {
                schema_version = 1,
                parameter_ranges = ranges,
                from_date = Box("OptimizeFromDateBox").Text,
                to_date = Box("OptimizeToDateBox").Text,
                initial_balance = Box("OptimizeBalanceBox").Text,
                spread_pips = Box("OptimizeSpreadBox").Text,
                commission_per_lot = Box("OptimizeCommissionBox").Text,
                min_trades = Box("MinTradesBox").Text,
                workers = Box("WorkersBox").Text,
                folds = Box("WalkForwardFoldsBox").Text,
                train_ratio = CurrentTrainRatio(),
                rolling = CurrentRolling()
            };

            await using var stream = await file.OpenWriteAsync();
            if (stream.CanSeek)
                stream.SetLength(0);
            await JsonSerializer.SerializeAsync(
                stream,
                payload,
                new JsonSerializerOptions { WriteIndented = true });
            await stream.FlushAsync();
            SetStateMessage($"Đã lưu preset: {file.Name}", Brushes.LightGreen);
        }
        catch (Exception ex)
        {
            SetStateMessage($"Lưu preset lỗi: {ex.Message}", Brushes.IndianRed);
        }
    }

    private async void LoadPreset_OnClick(object? sender, RoutedEventArgs e)
    {
        var storage = TopLevel.GetTopLevel(this)?.StorageProvider;
        if (storage is null || !storage.CanOpen)
            return;

        var files = await storage.OpenFilePickerAsync(
            new FilePickerOpenOptions
            {
                Title = "Tải Optimizer preset",
                AllowMultiple = false,
                FileTypeFilter = new[] { OptimizerPresetType }
            });
        var file = files.FirstOrDefault();
        if (file is null)
            return;

        try
        {
            await using var stream = await file.OpenReadAsync();
            using var doc = await JsonDocument.ParseAsync(stream);
            ApplyPreset(doc.RootElement);
            SetStateMessage($"Đã tải preset: {file.Name}", Brushes.LightGreen);
        }
        catch (Exception ex)
        {
            SetStateMessage($"Tải preset lỗi: {ex.Message}", Brushes.IndianRed);
        }
    }

    private void ApplyPreset(JsonElement root)
    {
        if (!root.TryGetProperty("parameter_ranges", out var ranges) ||
            ranges.ValueKind != JsonValueKind.Array)
        {
            throw new InvalidDataException("Preset thiếu parameter_ranges.");
        }

        _suppressInputEvents = true;
        try
        {
            foreach (var item in ranges.EnumerateArray())
            {
                string? path = item.TryGetProperty("path", out var p) ? p.GetString() : null;
                if (string.IsNullOrWhiteSpace(path))
                    continue;

                if (path.StartsWith("timeframes.", StringComparison.Ordinal))
                {
                    if (!item.TryGetProperty("values", out var values) ||
                        values.ValueKind != JsonValueKind.Array)
                        continue;
                    var list = values.EnumerateArray()
                        .Where(v => v.ValueKind == JsonValueKind.String)
                        .Select(v => v.GetString()!)
                        .Where(v => Timeframes.Contains(v))
                        .ToArray();
                    if (list.Length == 0)
                        continue;
                    string prefix = path.EndsWith("direction", StringComparison.Ordinal)
                        ? "DirectionTf"
                        : path.EndsWith("pullback", StringComparison.Ordinal)
                            ? "PullbackTf"
                            : "TriggerTf";
                    Combo(prefix + "MinCombo").SelectedItem = list.First();
                    Combo(prefix + "MaxCombo").SelectedItem = list.Last();
                    continue;
                }

                if (!TryPresetRange(item, out var min, out var max, out var step))
                    continue;

                switch (path)
                {
                    case "pullback.rsi_buy_level":
                        SetNumericRange("RsiBuyMinBox", "RsiBuyMaxBox", "RsiBuyStepBox", min, max, step);
                        break;
                    case "pullback.rsi_sell_level":
                        SetNumericRange("RsiSellMinBox", "RsiSellMaxBox", "RsiSellStepBox", min, max, step);
                        break;
                    case "trigger.rsi_reversal_delta":
                    case "trigger.z_reversal_delta":
                        if (path == _triggerDeltaPath)
                            SetNumericRange("RsiDeltaMinBox", "RsiDeltaMaxBox", "RsiDeltaStepBox", min, max, step);
                        break;
                    case "direction.ma_period":
                        SetNumericRange("EmaMinBox", "EmaMaxBox", "EmaStepBox", min, max, step);
                        break;
                    default:
                        if (path == _slPath)
                            SetNumericRange("SlMinBox", "SlMaxBox", "SlStepBox", min, max, step);
                        if (path == _tpPath)
                            SetNumericRange("TpMinBox", "TpMaxBox", "TpStepBox", min, max, step);
                        break;
                }
            }

            SetTextIfPresent(root, "from_date", "OptimizeFromDateBox");
            SetTextIfPresent(root, "to_date", "OptimizeToDateBox");
            SetTextIfPresent(root, "initial_balance", "OptimizeBalanceBox");
            SetTextIfPresent(root, "spread_pips", "OptimizeSpreadBox");
            SetTextIfPresent(root, "commission_per_lot", "OptimizeCommissionBox");
            SetTextIfPresent(root, "min_trades", "MinTradesBox");
            SetTextIfPresent(root, "workers", "WorkersBox");
            SetTextIfPresent(root, "folds", "WalkForwardFoldsBox");

            if (root.TryGetProperty("train_ratio", out var ratio) &&
                ratio.ValueKind == JsonValueKind.Number &&
                ratio.TryGetDouble(out var ratioValue))
            {
                SelectComboByTag("WalkForwardRatioCombo", ratioValue.ToString("0.00", CultureInfo.InvariantCulture));
            }
            if (root.TryGetProperty("rolling", out var rolling) &&
                rolling.ValueKind is JsonValueKind.True or JsonValueKind.False)
            {
                SelectComboByTag("WalkForwardRollingCombo", rolling.GetBoolean() ? "true" : "false");
            }

            UpdateCombinationPreview();
        }
        finally
        {
            _suppressInputEvents = false;
        }
    }

    private void ParameterSelection_OnChanged(
        object? sender,
        SelectionChangedEventArgs e)
    {
        if (_initialized && !_suppressInputEvents)
            UpdateCombinationPreview();
    }

    private void ParameterText_OnChanged(
        object? sender,
        TextChangedEventArgs e)
    {
        if (_initialized && !_suppressInputEvents)
            UpdateCombinationPreview();
    }

    private List<Dictionary<string, object>> BuildParameterRanges()
    {
        var ranges = new List<Dictionary<string, object>>
        {
            EnumRange("timeframes.direction", "DirectionTfMinCombo", "DirectionTfMaxCombo"),
            EnumRange("timeframes.pullback", "PullbackTfMinCombo", "PullbackTfMaxCombo"),
            EnumRange("timeframes.trigger", "TriggerTfMinCombo", "TriggerTfMaxCombo"),
        };

        if (_includeRsiRows)
        {
            ranges.Add(NumericRange(
                "pullback.rsi_buy_level",
                "RsiBuyMinBox", "RsiBuyMaxBox", "RsiBuyStepBox"));
            ranges.Add(NumericRange(
                "pullback.rsi_sell_level",
                "RsiSellMinBox", "RsiSellMaxBox", "RsiSellStepBox"));
        }
        if (_triggerDeltaPath is not null)
        {
            ranges.Add(NumericRange(
                _triggerDeltaPath,
                "RsiDeltaMinBox", "RsiDeltaMaxBox", "RsiDeltaStepBox"));
        }
        if (_includeMaPeriod)
        {
            ranges.Add(NumericRange(
                "direction.ma_period",
                "EmaMinBox", "EmaMaxBox", "EmaStepBox"));
        }
        if (_slPath is not null)
        {
            ranges.Add(NumericRange(
                _slPath,
                "SlMinBox", "SlMaxBox", "SlStepBox"));
        }
        if (_tpPath is not null)
        {
            ranges.Add(NumericRange(
                _tpPath,
                "TpMinBox", "TpMaxBox", "TpStepBox"));
        }

        if (ranges.Count == 0)
            throw new InvalidDataException("Không có tham số nào khả dụng để tối ưu.");
        return ranges;
    }

    private Dictionary<string, object> EnumRange(
        string path,
        string minCombo,
        string maxCombo)
    {
        int min = Combo(minCombo).SelectedIndex;
        int max = Combo(maxCombo).SelectedIndex;
        if (min < 0 || max < 0 || max < min)
            throw new InvalidDataException($"{path}: phạm vi timeframe không hợp lệ.");

        return new Dictionary<string, object>
        {
            ["path"] = path,
            ["values"] = Timeframes[min..(max + 1)]
        };
    }

    private Dictionary<string, object> NumericRange(
        string path,
        string minBox,
        string maxBox,
        string stepBox)
    {
        if (!TryNumber(Box(minBox).Text, out var min) ||
            !TryNumber(Box(maxBox).Text, out var max) ||
            !TryNumber(Box(stepBox).Text, out var step) ||
            step <= 0 ||
            max < min)
        {
            throw new InvalidDataException($"{path}: min/max/step không hợp lệ.");
        }

        return new Dictionary<string, object>
        {
            ["path"] = path,
            ["min"] = min,
            ["max"] = max,
            ["step"] = step
        };
    }

    private void UpdateCombinationPreview()
    {
        try
        {
            long total = 1;
            foreach (var range in BuildParameterRanges())
            {
                if (range.TryGetValue("values", out var values) &&
                    values is Array array)
                {
                    total *= array.Length;
                }
                else
                {
                    double min = Convert.ToDouble(range["min"], CultureInfo.InvariantCulture);
                    double max = Convert.ToDouble(range["max"], CultureInfo.InvariantCulture);
                    double step = Convert.ToDouble(range["step"], CultureInfo.InvariantCulture);
                    total *= (long)Math.Floor((max - min) / step + 1e-9) + 1;
                }
                if (total > 50_000)
                    break;
            }

            Text("CombinationPreviewText").Text = $"Tổ hợp: {total:N0}";
            Text("CombinationPreviewText").Foreground =
                total > 50_000 ? Brushes.IndianRed : Brushes.DeepSkyBlue;
        }
        catch
        {
            Text("CombinationPreviewText").Text = "Tổ hợp: —";
            Text("CombinationPreviewText").Foreground = Brushes.Gold;
        }
    }

    private bool TryContextValues(
        out string fromDate,
        out string toDate,
        out double balance,
        out double spread,
        out double commission,
        out int minTrades,
        out int workers)
    {
        fromDate = Box("OptimizeFromDateBox").Text?.Trim() ?? string.Empty;
        toDate = Box("OptimizeToDateBox").Text?.Trim() ?? string.Empty;
        balance = 0;
        spread = 0;
        commission = 0;
        minTrades = 0;
        workers = 0;

        if (!DateOnly.TryParseExact(fromDate, "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out _) ||
            !DateOnly.TryParseExact(toDate, "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out _))
        {
            SetStateMessage("Ngày phải theo YYYY-MM-DD.", Brushes.IndianRed);
            return false;
        }

        if (!TryNumber(Box("OptimizeBalanceBox").Text, out balance) || balance <= 0 ||
            !TryNumber(Box("OptimizeSpreadBox").Text, out spread) || spread < 0 ||
            !TryNumber(Box("OptimizeCommissionBox").Text, out commission) || commission < 0 ||
            !int.TryParse(Box("MinTradesBox").Text, NumberStyles.Integer, CultureInfo.InvariantCulture, out minTrades) || minTrades < 1 ||
            !int.TryParse(Box("WorkersBox").Text, NumberStyles.Integer, CultureInfo.InvariantCulture, out workers) || workers < 1)
        {
            SetStateMessage("Vốn/spread/commission/min-trades/workers không hợp lệ.", Brushes.IndianRed);
            return false;
        }

        return true;
    }

    private double CurrentTrainRatio()
    {
        if (Combo("WalkForwardRatioCombo").SelectedItem is ComboBoxItem { Tag: string tag } &&
            double.TryParse(tag, NumberStyles.Float, CultureInfo.InvariantCulture, out var value))
        {
            return value;
        }
        return 0.70;
    }

    private bool CurrentRolling()
    {
        return Combo("WalkForwardRollingCombo").SelectedItem is ComboBoxItem { Tag: string tag } &&
               string.Equals(tag, "true", StringComparison.OrdinalIgnoreCase);
    }

    private string CurrentHeatmapMetric()
    {
        return Combo("HeatmapMetricCombo").SelectedItem is ComboBoxItem { Tag: string tag }
            ? tag
            : "net_profit";
    }

    private void SetTimeframeRange(
        string minName,
        string maxName,
        string current,
        int lowerOffset,
        int upperOffset)
    {
        int index = Array.IndexOf(Timeframes, current);
        if (index < 0)
            index = 0;
        Combo(minName).SelectedIndex = Math.Clamp(index + lowerOffset, 0, Timeframes.Length - 1);
        Combo(maxName).SelectedIndex = Math.Clamp(index + upperOffset, 0, Timeframes.Length - 1);
        if (Combo(maxName).SelectedIndex < Combo(minName).SelectedIndex)
            Combo(maxName).SelectedIndex = Combo(minName).SelectedIndex;
    }

    private void SetNumericRange(
        string minName,
        string maxName,
        string stepName,
        double min,
        double max,
        double step)
    {
        Box(minName).Text = Format(min);
        Box(maxName).Text = Format(max);
        Box(stepName).Text = Format(step);
    }

    private void SetRowEnabled(bool enabled, params string[] names)
    {
        foreach (var name in names)
            Box(name).IsEnabled = enabled;
    }

    private static string? GetString(JsonElement root, params string[] path)
    {
        return TryNested(root, path, out var value) &&
               value.ValueKind == JsonValueKind.String
            ? value.GetString()
            : null;
    }

    private static double? GetDouble(JsonElement root, params string[] path)
    {
        return TryNested(root, path, out var value) &&
               value.ValueKind == JsonValueKind.Number &&
               value.TryGetDouble(out var parsed)
            ? parsed
            : null;
    }

    private static bool? GetBool(JsonElement root, params string[] path)
    {
        if (!TryNested(root, path, out var value))
            return null;
        return value.ValueKind switch
        {
            JsonValueKind.True => true,
            JsonValueKind.False => false,
            _ => null
        };
    }

    private static bool TryNested(
        JsonElement root,
        IReadOnlyList<string> path,
        out JsonElement value)
    {
        value = root;
        foreach (var part in path)
        {
            if (value.ValueKind != JsonValueKind.Object ||
                !value.TryGetProperty(part, out value))
            {
                return false;
            }
        }
        return true;
    }

    private static bool TryPresetRange(
        JsonElement item,
        out double min,
        out double max,
        out double step)
    {
        min = max = step = 0;
        return item.TryGetProperty("min", out var a) && a.TryGetDouble(out min) &&
               item.TryGetProperty("max", out var b) && b.TryGetDouble(out max) &&
               item.TryGetProperty("step", out var c) && c.TryGetDouble(out step);
    }

    private void SetTextIfPresent(JsonElement root, string property, string boxName)
    {
        if (!root.TryGetProperty(property, out var value))
            return;
        Box(boxName).Text = value.ValueKind == JsonValueKind.String
            ? value.GetString()
            : value.ToString();
    }

    private void SelectComboByTag(string comboName, string tag)
    {
        var combo = Combo(comboName);
        int index = 0;
        foreach (var raw in combo.Items)
        {
            if (raw is ComboBoxItem item &&
                string.Equals(item.Tag?.ToString(), tag, StringComparison.OrdinalIgnoreCase))
            {
                combo.SelectedIndex = index;
                return;
            }
            index++;
        }
    }

    private static void AddHeatmapLabel(Grid grid, int column, int row, string value)
    {
        var label = new TextBlock
        {
            Text = value,
            FontSize = 9,
            Foreground = new SolidColorBrush(Color.Parse("#A8C1D9")),
            HorizontalAlignment = HorizontalAlignment.Center,
            VerticalAlignment = VerticalAlignment.Center,
            TextTrimming = TextTrimming.CharacterEllipsis
        };
        Grid.SetColumn(label, column);
        Grid.SetRow(label, row);
        grid.Children.Add(label);
    }

    private static IBrush HeatColor(
        double value,
        double min,
        double max,
        bool higherIsBetter)
    {
        double t = Math.Abs(max - min) < 1e-12
            ? 0.5
            : Math.Clamp((value - min) / (max - min), 0, 1);
        if (!higherIsBetter)
            t = 1.0 - t;

        byte r;
        byte g;
        byte b;
        if (t < 0.5)
        {
            double u = t / 0.5;
            r = 220;
            g = (byte)(45 + 170 * u);
            b = 55;
        }
        else
        {
            double u = (t - 0.5) / 0.5;
            r = (byte)(220 - 185 * u);
            g = (byte)(215 - 10 * u);
            b = (byte)(55 + 60 * u);
        }
        return new SolidColorBrush(Color.FromRgb(r, g, b));
    }

    private static int FindJsonValueIndex(
        IReadOnlyList<JsonElement> values,
        JsonElement target)
    {
        string targetText = JsonSerializer.Serialize(target);
        for (int i = 0; i < values.Count; i++)
        {
            if (JsonSerializer.Serialize(values[i]) == targetText)
                return i;
        }
        return -1;
    }

    private static string JsonValueText(JsonElement value)
    {
        return value.ValueKind == JsonValueKind.String
            ? value.GetString() ?? string.Empty
            : value.ToString();
    }

    private static string ParameterSummary(
        IReadOnlyDictionary<string, JsonElement> parameters)
    {
        return string.Join(
            " | ",
            parameters.Take(5).Select(
                item => $"{ShortParameterLabel(item.Key)}={JsonValueText(item.Value)}"));
    }

    private static string ShortParameterLabel(string path) => path switch
    {
        "timeframes.direction" => "Dir TF",
        "timeframes.pullback" => "PB TF",
        "timeframes.trigger" => "Trig TF",
        "direction.ma_period" => "MA",
        "pullback.rsi_buy_level" => "RSI Buy",
        "pullback.rsi_sell_level" => "RSI Sell",
        "trigger.rsi_reversal_delta" => "RSI Δ",
        "trigger.z_reversal_delta" => "Z Δ",
        "stop_loss.structure_lookback" => "SL Lookback",
        "stop_loss.fixed_price_units" => "SL Fixed",
        "take_profit.fixed_price_units" => "TP Fixed",
        "take_profit.rr_ratio" => "TP RR",
        _ => path.Split('.').Last()
    };

    private static string PhaseLabel(OptimizerStatusSnapshot status)
    {
        string fold = status.FoldCount > 0
            ? $" • fold {status.CurrentFold}/{status.FoldCount}"
            : string.Empty;
        return status.Phase switch
        {
            "PARAMETER_SWEEP" => $"Đang backtest các tổ hợp tham số{fold}",
            "TRAIN_OPTIMIZATION" => $"Đang tối ưu TRAIN{fold}",
            "TEST_EVALUATION" => $"Đang đánh giá TEST out-of-sample{fold}",
            "STOPPING" => "Đang dừng sau các candidate đang chạy...",
            "COMPLETED" => "Kết quả đã được lưu.",
            "CANCELLED" => "Job đã hủy; không lưu như kết quả hoàn tất.",
            "FAILED" => status.Error ?? "Optimizer lỗi.",
            _ => "Chọn dataset và cấu hình phạm vi tham số."
        };
    }

    private void SetStateMessage(string message, IBrush brush)
    {
        Text("OptimizerPhaseText").Text = message;
        Text("OptimizerStateText").Foreground = brush;
    }

    private static string Money(double value) =>
        $"{value:+0.00;-0.00;0.00}";

    private static IBrush ProfitBrush(double value) =>
        value > 0
            ? Brushes.LightGreen
            : value < 0
                ? Brushes.IndianRed
                : Brushes.LightGray;

    private static string Format(double value) =>
        value.ToString("0.########", CultureInfo.InvariantCulture);

    private static bool TryNumber(string? text, out double value)
    {
        if (double.TryParse(text, NumberStyles.Float, CultureInfo.InvariantCulture, out value))
            return true;
        return double.TryParse(text, NumberStyles.Float, CultureInfo.CurrentCulture, out value);
    }

    private static string FormatDuration(double seconds)
    {
        if (!double.IsFinite(seconds) || seconds < 0)
            return "—";
        var span = TimeSpan.FromSeconds(seconds);
        if (span.TotalDays >= 1)
            return $"{(int)span.TotalDays}d {span.Hours:00}:{span.Minutes:00}";
        return $"{(int)span.TotalHours:00}:{span.Minutes:00}:{span.Seconds:00}";
    }

    private static string ShortHash(string value) =>
        string.IsNullOrWhiteSpace(value)
            ? "—"
            : value[..Math.Min(10, value.Length)];

    private static string Compact(double value)
    {
        double abs = Math.Abs(value);
        if (abs >= 1_000_000)
            return $"{value / 1_000_000.0:0.0}M";
        if (abs >= 1_000)
            return $"{value / 1_000.0:0.0}K";
        return value.ToString("0.##", CultureInfo.InvariantCulture);
    }

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

    private static Border RowBorder(Grid grid) => new()
    {
        Background = new SolidColorBrush(Color.Parse("#06192C")),
        BorderBrush = new SolidColorBrush(Color.Parse("#123D5D")),
        BorderThickness = new Thickness(0, 1, 0, 0),
        Child = grid
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
            Foreground = brush ?? new SolidColorBrush(Color.Parse("#D9E5F2")),
            FontSize = 10.5,
            VerticalAlignment = VerticalAlignment.Center,
            Margin = new Thickness(6, 5),
            TextTrimming = TextTrimming.CharacterEllipsis
        };
        Grid.SetColumn(text, column);
        grid.Children.Add(text);
    }

    private TextBlock Text(string name) =>
        this.FindControl<TextBlock>(name)
        ?? throw new InvalidOperationException($"Missing Optimizer TextBlock: {name}");

    private TextBox Box(string name) =>
        this.FindControl<TextBox>(name)
        ?? throw new InvalidOperationException($"Missing Optimizer TextBox: {name}");

    private ComboBox Combo(string name) =>
        this.FindControl<ComboBox>(name)
        ?? throw new InvalidOperationException($"Missing Optimizer ComboBox: {name}");

    private Button Button(string name) =>
        this.FindControl<Button>(name)
        ?? throw new InvalidOperationException($"Missing Optimizer Button: {name}");

    private StackPanel Panel(string name) =>
        this.FindControl<StackPanel>(name)
        ?? throw new InvalidOperationException($"Missing Optimizer panel: {name}");

    private Grid GridControl(string name) =>
        this.FindControl<Grid>(name)
        ?? throw new InvalidOperationException($"Missing Optimizer Grid: {name}");

    private ProgressBar Progress(string name) =>
        this.FindControl<ProgressBar>(name)
        ?? throw new InvalidOperationException($"Missing Optimizer ProgressBar: {name}");
}
