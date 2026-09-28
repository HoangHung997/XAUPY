using System.Globalization;
using System.Text.Json;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Media.Imaging;
using Avalonia.Platform.Storage;
using XAUPY.Ipc;

namespace XAUPY.Desktop;

public sealed partial class MarketChartControl
{
    private int _visibleBars=64, _panBars;
    private int[] _emaPeriods=[50,20,10];
    private int _rsiPeriod=14,_zPeriod=20;
    private bool _archiveMode;
    private MarketBar[]? _comparisonBars;
    private string? _comparisonSymbol;
    private Point? _dragStart;
    private int _dragStartPan;
    private OverviewSnapshot? _latestSnapshot;
    private MarketChartControl? _fullScreenChart;

    public MarketChartControl()
    {
        Focusable=true;
        var menu=new ContextMenu();
        void Item(string label,Func<Task> action) { var item=new MenuItem {Header=label}; item.Click+=async (_,_)=>{try{await action();}catch(Exception ex){await ShowChartErrorAsync(ex.Message);}};menu.Items.Add(item); }
        Item("Tải toàn bộ lịch sử CSV/JSON…",()=>LoadHistoryFileAsync(false));
        Item("So sánh với tài sản khác…",()=>LoadHistoryFileAsync(true));
        Item("Cài đặt EMA / RSI / Z…",ConfigureIndicatorsAsync);
        Item("Lưu biểu đồ PNG…",SaveChartAsync);
        Item("Toàn màn hình (Esc để thoát)",ShowFullScreenAsync);
        var frames=new MenuItem {Header="Khung thời gian"};
        foreach(string frame in Timeframes){var item=new MenuItem {Header=frame};item.Click+=(_,_)=>SelectTimeframe(frame);frames.Items.Add(item);}menu.Items.Add(frames);
        Item("Về giá hiện tại",()=>{_panBars=0;if(_archiveMode)_history.Clear();_archiveMode=false;if(_latestSnapshot is not null)SetSnapshot(_latestSnapshot);InvalidateVisual();return Task.CompletedTask;});
        ContextMenu=menu;
    }

    protected override void OnPointerWheelChanged(PointerWheelEventArgs e)
    {
        base.OnPointerWheelChanged(e);
        if(e.KeyModifiers.HasFlag(KeyModifiers.Shift)) _panBars=Math.Max(0,_panBars+(int)(e.Delta.Y*10));
        else _visibleBars=Math.Clamp((int)Math.Round(_visibleBars*(e.Delta.Y>0?.8:1.25)),10,1000);
        e.Handled=true; InvalidateVisual();
    }
    protected override void OnPointerPressed(PointerPressedEventArgs e)
    {
        base.OnPointerPressed(e);
        if(!e.GetCurrentPoint(this).Properties.IsLeftButtonPressed) return;
        Focus(); _dragStart=e.GetPosition(this); _dragStartPan=_panBars; e.Pointer.Capture(this); e.Handled=true;
    }
    protected override void OnPointerMoved(PointerEventArgs e)
    {
        base.OnPointerMoved(e);
        if(_dragStart is not {} start) return;
        _panBars=Math.Max(0,_dragStartPan+(int)((e.GetPosition(this).X-start.X)/Math.Max(1,Bounds.Width)*_visibleBars));
        InvalidateVisual();
    }
    protected override void OnPointerReleased(PointerReleasedEventArgs e)
    { base.OnPointerReleased(e); _dragStart=null; e.Pointer.Capture(null); }
    protected override void OnKeyDown(KeyEventArgs e)
    {
        base.OnKeyDown(e);
        if(e.Key==Key.Left) _panBars+=Math.Max(1,_visibleBars/5);
        else if(e.Key==Key.Right) _panBars=Math.Max(0,_panBars-Math.Max(1,_visibleBars/5));
        else if(e.Key==Key.End) _panBars=0;
        else if(e.Key==Key.Home && _history.TryGetValue(_timeframe,out var bars)) _panBars=Math.Max(0,bars.Count-_visibleBars);
        else return;
        e.Handled=true;InvalidateVisual();
    }

    private async Task LoadHistoryFileAsync(bool comparison)
    {
        var top=TopLevel.GetTopLevel(this); if(top is null) return;
        var files=await top.StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions {Title=comparison?"Chọn lịch sử tài sản so sánh":"Mở toàn bộ lịch sử",FileTypeFilter=new[]{new FilePickerFileType("Nến CSV/JSON"){Patterns=new[]{"*.csv","*.json"}}} });
        if(files.Count==0) return;
        var parsed=await Task.Run(()=>ReadChartData(files[0].Path.LocalPath));
        if(comparison) { _comparisonBars=parsed.Bars;_comparisonSymbol=parsed.Symbol+" "+parsed.Timeframe;_comparisonTimeframe=null; }
        else
        {
            _archiveMode=true;_symbol=parsed.Symbol;_timeframe=parsed.Timeframe;_userSelectedTimeframe=true;
            _history.Clear();_history[_timeframe]=new SortedDictionary<long,MarketBar>(parsed.Bars.ToDictionary(b=>b.Time));
            _formingBars=new Dictionary<string,MarketBar>();_bid=null;_connected=false;_panBars=0;
        }
        UpdateToolbar();InvalidateVisual();
        ToolTip.SetTip(this,$"{parsed.Symbol} {parsed.Timeframe} • {parsed.Bars.Length:N0} nến • cuộn để zoom, kéo để xem lịch sử, Home/End, chuột phải để mở công cụ.");
    }
    internal static (string Symbol,string Timeframe,MarketBar[] Bars) ReadChartData(string path)
    {
        string symbol=Path.GetFileNameWithoutExtension(path),tf="M1";
        var bars=new List<MarketBar>();
        if(Path.GetExtension(path).Equals(".json",StringComparison.OrdinalIgnoreCase))
        {
            using var doc=JsonDocument.Parse(File.ReadAllText(path));
            var root=doc.RootElement;
            symbol=root.GetProperty("symbol").GetString()!;
            if(root.TryGetProperty("timeframe",out var timeframe))tf=timeframe.GetString()!;
            foreach(var b in root.GetProperty("bars").EnumerateArray())
                bars.Add(new MarketBar(b.GetProperty("time").GetInt64(),b.GetProperty("open").GetDouble(),b.GetProperty("high").GetDouble(),b.GetProperty("low").GetDouble(),b.GetProperty("close").GetDouble(),b.TryGetProperty("tick_volume",out var volume)?volume.GetInt64():0));
        }
        else
        {
            using var reader=new StreamReader(path);
            var header=(reader.ReadLine() ?? "").TrimStart('\uFEFF').Split(',');
            int Index(string name)=>Array.IndexOf(header,name);
            foreach(var name in new[]{"time","open","high","low","close"}) if(Index(name)<0)throw new InvalidDataException("Thiếu cột "+name);
            string? line;
            while((line=reader.ReadLine()) is not null)
            {
                if(string.IsNullOrWhiteSpace(line))continue;
                var row=line.Split(',');
                double Number(string name)=>double.Parse(row[Index(name)],CultureInfo.InvariantCulture);
                if(Index("symbol")>=0)symbol=row[Index("symbol")];
                if(Index("timeframe")>=0)tf=row[Index("timeframe")];
                bars.Add(new MarketBar(long.Parse(row[Index("time")],CultureInfo.InvariantCulture),Number("open"),Number("high"),Number("low"),Number("close"),Index("tick_volume")>=0?(long)Number("tick_volume"):0));
            }
            var manifest=Path.Combine(Path.GetDirectoryName(path)!,"manifest.json");
            if(File.Exists(manifest))
            {
                using var doc=JsonDocument.Parse(File.ReadAllText(manifest));
                foreach(var entry in doc.RootElement.GetProperty("timeframes").EnumerateObject())
                    if(entry.Value.TryGetProperty("path",out var file) && Path.GetFullPath(file.GetString()!)==Path.GetFullPath(path)) {tf=entry.Name;symbol=doc.RootElement.GetProperty("symbol").GetString()!;break;}
            }
        }
        if(bars.Count==0 || !Timeframes.Contains(tf) || bars.Any(b=>!Valid(b) || b.TickVolume<0) || bars.Zip(bars.Skip(1)).Any(p=>p.First.Time>=p.Second.Time))
            throw new InvalidDataException("Nến phải hợp lệ, tăng dần, không trùng thời gian và thuộc khung được hỗ trợ.");
        return(symbol,tf,bars.ToArray());
    }

    private async Task ConfigureIndicatorsAsync()
    {
        if(TopLevel.GetTopLevel(this) is not Window owner)return;
        var ema=new TextBox {Text=string.Join(',',_emaPeriods)};
        var rsi=new TextBox {Text=_rsiPeriod.ToString()}; var z=new TextBox {Text=_zPeriod.ToString()};
        var show=new CheckBox {[LocalizationService.TextProperty] = "Hiển thị chỉ báo",IsChecked=_showIndicators};
        var status=new TextBlock {Foreground=Brushes.OrangeRed,TextWrapping=TextWrapping.Wrap};var save=new Button {[LocalizationService.TextProperty] = "Áp dụng trên biểu đồ"};
        var dialog=new Window {Title="Chỉ báo biểu đồ",Width=430,Height=370,WindowStartupLocation=WindowStartupLocation.CenterOwner};
        save.Click+=(_,_)=>
        {
            try
            {
                var periods=ema.Text!.Split(',',StringSplitOptions.RemoveEmptyEntries).Select(v=>int.Parse(v.Trim())).ToArray();
                int rp=int.Parse(rsi.Text!),zp=int.Parse(z.Text!);
                if(periods.Length>3 || periods.Any(p=>p<2 || p>2000) || rp<2 || rp>2000 || zp<2 || zp>2000)throw new InvalidDataException("Tối đa 3 EMA; mỗi chu kỳ từ 2 đến 2000.");
                _emaPeriods=periods;_rsiPeriod=rp;_zPeriod=zp;_showIndicators=show.IsChecked==true;InvalidateVisual();dialog.Close();
            }catch(Exception ex){status.Text=ex.Message;}
        };
        dialog.Content=new StackPanel {Margin=new Thickness(16),Spacing=8,Children={show,new TextBlock {[LocalizationService.TextProperty] = "EMA (ngăn bởi dấu phẩy)"},ema,new TextBlock {Text="RSI Wilder"},rsi,new TextBlock {[LocalizationService.TextProperty] = "Z-score (độ lệch chuẩn tổng thể)"},z,status,save}};
        await dialog.ShowDialog(owner);
    }
    internal static (double? Rsi,double? Z) ChartMetrics(MarketBar[] bars,int rsiPeriod,int zPeriod)
    {
        double? rsi=null,z=null;
        if(bars.Length>rsiPeriod)
        {
            double gain=0,loss=0;
            for(int i=1;i<=rsiPeriod;i++){double delta=bars[i].Close-bars[i-1].Close;gain+=Math.Max(0,delta)/rsiPeriod;loss+=Math.Max(0,-delta)/rsiPeriod;}
            for(int i=rsiPeriod+1;i<bars.Length;i++){double delta=bars[i].Close-bars[i-1].Close;gain=(gain*(rsiPeriod-1)+Math.Max(0,delta))/rsiPeriod;loss=(loss*(rsiPeriod-1)+Math.Max(0,-delta))/rsiPeriod;}
            rsi=loss==0 ? gain==0?50:100 : 100-100/(1+gain/loss);
        }
        if(bars.Length>=zPeriod)
        {
            var values=bars.TakeLast(zPeriod).Select(b=>b.Close).ToArray();double mean=values.Average(),sigma=Math.Sqrt(values.Average(v=>(v-mean)*(v-mean)));
            z=sigma>0?(values[^1]-mean)/sigma:0;
        }
        return(rsi,z);
    }
    private async Task SaveChartAsync()
    {
        var top=TopLevel.GetTopLevel(this);if(top is null || Bounds.Width<1 || Bounds.Height<1)return;
        var file=await top.StorageProvider.SaveFilePickerAsync(new FilePickerSaveOptions {Title="Lưu biểu đồ PNG",SuggestedFileName=$"{_symbol}-{_timeframe}-{DateTime.Now:yyyyMMdd-HHmmss}.png",DefaultExtension="png"});
        if(file is null)return;
        using var bitmap=new RenderTargetBitmap(new PixelSize((int)Math.Ceiling(Bounds.Width),(int)Math.Ceiling(Bounds.Height)),new Vector(96,96));
        bitmap.Render(this);await using var stream=await file.OpenWriteAsync();if(stream.CanSeek)stream.SetLength(0);bitmap.Save(stream,PngBitmapEncoderOptions.Default);
    }
    private async Task ShowFullScreenAsync()
    {
        if(TopLevel.GetTopLevel(this) is not Window owner || _fullScreenChart is not null)return;
        var chart=new MarketChartControl {_timeframe=_timeframe,_symbol=_symbol,_archiveMode=_archiveMode,_connected=_connected,_bid=_bid,
            _visibleBars=_visibleBars,_panBars=_panBars,_emaPeriods=(int[])_emaPeriods.Clone(),_rsiPeriod=_rsiPeriod,_zPeriod=_zPeriod,
            _showIndicators=_showIndicators,_formingBars=_formingBars,_comparisonBars=_comparisonBars,_comparisonSymbol=_comparisonSymbol,
            _comparisonTimeframe=_comparisonTimeframe,_lineMode=_lineMode,_userSelectedTimeframe=_userSelectedTimeframe,_latestSnapshot=_latestSnapshot};
        foreach(var (tf,bars) in _history)chart._history[tf]=new SortedDictionary<long,MarketBar>(bars);
        var window=new Window {Title=$"{_symbol} {_timeframe} • Esc để thoát",WindowState=WindowState.FullScreen,Content=chart};
        window.KeyDown+=(_,e)=>{if(e.Key==Key.Escape)window.Close();};_fullScreenChart=chart;
        try{await window.ShowDialog(owner);}finally{_fullScreenChart=null;}
    }
    private async Task ShowChartErrorAsync(string message)
    {
        if(TopLevel.GetTopLevel(this) is not Window owner)return;
        var close=new Button {[LocalizationService.TextProperty] = "Đóng"};var window=new Window {Title="Biểu đồ",Width=520,Height=200,WindowStartupLocation=WindowStartupLocation.CenterOwner};
        close.Click+=(_,_)=>window.Close();window.Content=new StackPanel {Margin=new Thickness(20),Spacing=15,Children={new TextBlock {Text=message,TextWrapping=TextWrapping.Wrap},close}};await window.ShowDialog(owner);
    }
    private async Task RunChartActionAsync(Func<Task> action)
    {try{await action();}catch(Exception ex){await ShowChartErrorAsync(ex.Message);}}
}
