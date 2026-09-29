using System.Net.Sockets;
using System.Reflection;
using System.Text;
using System.Text.Json;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Media.Imaging;
using Avalonia.Threading;
using Avalonia.VisualTree;
using XAUPY.Desktop;
using XAUPY.Ipc;

internal static class CaptureAudit
{
    // All market/account values below are test-only. No real terminal is opened.
    public static int Run(string directory, int port)
    {
        Directory.CreateDirectory(directory);
        var window = new MainWindow { Width=1672, Height=941, WindowState=WindowState.Normal };
        var supervisor=(EngineProcessSupervisor)typeof(MainWindow).GetField("_engineSupervisor",BindingFlags.Instance|BindingFlags.NonPublic)!.GetValue(window)!;
        TcpClient? client=null;StreamReader? reader=null;StreamWriter? writer=null;
        var pages=new Dictionary<string,string> {
            ["overview"]="NavOverview",["configuration"]="NavConfiguration",["strategy"]="NavStrategy",
            ["monitoring"]="NavMonitoring",["orders"]="NavOrders",["backtest"]="NavBacktest",
            ["optimization"]="NavOptimization",["logs"]="NavLogs",["tools"]="NavTools",["settings"]="NavSettings" };
        var report=new List<object>();
        string session=Guid.NewGuid().ToString();
        JsonElement Exchange(string type, object payload)
        {
            var message=ProtocolEnvelope.Create(type,payload);
            writer!.WriteLine(message.ToJson());
            var reply=ProtocolEnvelope.Parse(reader!.ReadLine() ?? throw new EndOfStreamException());
            if(reply.RequestId!=message.RequestId || reply.Type=="error") throw new InvalidDataException(reply.ToJson());
            return reply.Payload;
        }
        void Pump(int milliseconds)
        {
            long until=Environment.TickCount64+milliseconds;
            while(Environment.TickCount64<until){Dispatcher.UIThread.RunJobs();Thread.Sleep(10);}
            Dispatcher.UIThread.RunJobs();
        }
        void Snapshot()
        {
            long now=DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            var spans=new Dictionary<string,long> { ["M1"]=60,["M3"]=180,["M5"]=300,["M15"]=900,["M30"]=1800,["H1"]=3600,["H2"]=7200,["H4"]=14400,["D1"]=86400 };
            var history=spans.ToDictionary(kv=>kv.Key,kv=>Enumerable.Range(0,120).Select(i=> {
                double value=4200+Math.Sin(i/8.0)*3+i*.025;
                return new { time=(now/kv.Value-120+i)*kv.Value,open=value-.15,high=value+.45,low=value-.5,close=value,tick_volume=100+i };
            }).ToArray());
            Exchange("bridge_snapshot",new { bridge_version="1.021",execution_capable=true,demo_once_capable=true,
                bridge_session_id=session,account_login=700001,account_server="ISOLATED-UI-FIXTURE",symbol="XAUUSD",magic=991188,
                account_trade_mode="DEMO",terminal_connected=true,server_time=now,tick_time_msc=now*1000,
                server_utc_offset_seconds=0,bid=4202.25,ask=4202.45,point=.01,tick_size=.01,tick_value=1.0,tick_value_loss=1.0,
                volume_min=.01,volume_max=100.0,volume_step=.01,stops_level=10,freeze_level=0,
                balance=10000.0,equity=10000.0,margin_free=10000.0,account_currency="USD",account_leverage=100,
                positions=Array.Empty<object>(),orders=Array.Empty<object>(),deals=Array.Empty<object>(),
                guardian=new { execution_locked=true,execution_ready=false,reason="USER_STOPPED",max_volume=.1 },
                demo_once_guard=new {history_complete=true,broker_day_start=now/86400*86400,trades_today=0,consecutive_losses=0,last_exit_time=0,day_start_balance=10000.0,daily_realized=0.0},
                bars=history.ToDictionary(kv=>kv.Key,kv=>kv.Value[^1]),bar_history=history });
        }
        try
        {
            window.Show();
            long until=Environment.TickCount64+30000;
            while(supervisor.State!=EngineConnectionState.Ready && Environment.TickCount64<until)Pump(50);
            if(supervisor.State!=EngineConnectionState.Ready)throw new TimeoutException("Isolated capture Engine did not become READY");
            client=new TcpClient();client.Connect("127.0.0.1",port);client.ReceiveTimeout=15000;
            reader=new StreamReader(client.GetStream(),Encoding.UTF8,leaveOpen:true);
            writer=new StreamWriter(client.GetStream(),new UTF8Encoding(false),leaveOpen:true){AutoFlush=true,NewLine="\n"};
            Exchange("bridge_hello",new {component="mt5-bridge",bridge_version="1.021",symbol="XAUUSD",execution_capable=true,demo_once_capable=true,bridge_session_id=session});
            Snapshot();Pump(2200);
            foreach(var page in pages)
            {
                var button=window.FindControl<Button>(page.Value) ?? throw new InvalidOperationException(page.Value);
                button.RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
                for(int i=0;i<5;i++){Snapshot();Pump(300);}
                using var bitmap=new RenderTargetBitmap(new PixelSize((int)window.Bounds.Width,(int)window.Bounds.Height),new Vector(96,96));
                bitmap.Render(window);bitmap.Save(Path.Combine(directory,page.Key+".png"),PngBitmapEncoderOptions.Default);
                var controls=window.GetVisualDescendants().OfType<Control>().Where(c=>c.IsEffectivelyVisible && !string.IsNullOrEmpty(c.Name))
                    .Select(c=>new {name=c.Name,type=c.GetType().Name,enabled=c.IsEffectivelyEnabled,
                        width=c.Bounds.Width,height=c.Bounds.Height,location=c.TranslatePoint(default,window)?.ToString()}).ToArray();
                report.Add(new {page=page.Key,control_count=controls.Length,controls});
                if(page.Key=="orders")
                {
                    var confirmation=window.FindControl<OrdersPositionsDashboard>("OrdersPositionsDashboard")!.FindControl<CheckBox>("ManualConfirmCheck")!;
                    var buy=window.FindControl<OrdersPositionsDashboard>("OrdersPositionsDashboard")!.FindControl<Button>("MarketBuyButton")!;
                    var point=confirmation.TranslatePoint(default,window) ?? throw new InvalidOperationException("Confirmation unattached");
                    var buyPoint=buy.TranslatePoint(default,window) ?? throw new InvalidOperationException("BUY unattached");
                    if(point.Y<0 || point.Y+confirmation.Bounds.Height>window.Bounds.Height || point.Y>=buyPoint.Y || buyPoint.Y+buy.Bounds.Height>window.Bounds.Height-24)
                        throw new InvalidOperationException("Manual confirmation is hidden or below BUY at reference viewport");
                }
                if(supervisor.Execution.Enabled)throw new InvalidOperationException("Capture must never enable execution");
                Console.WriteLine("PASS isolated headless render "+page.Key);
            }
            File.WriteAllText(Path.Combine(directory,"capture-manifest.json"),JsonSerializer.Serialize(new {
                scope="HEADLESS ISOLATED FIXTURE; NOT NATIVE MT5 OR PIXEL-PARITY ACCEPTANCE",timestamp=DateTimeOffset.UtcNow,
                width=window.Bounds.Width,height=window.Bounds.Height,pages=report,broker_connected=false,execution_enabled=false
            },new JsonSerializerOptions{WriteIndented=true}));
            return 0;
        }
        finally
        {
            writer?.Dispose();reader?.Dispose();client?.Dispose();
            var stopping=supervisor.StopAsync();
            long until=Environment.TickCount64+15000;
            while(!stopping.IsCompleted && Environment.TickCount64<until)Pump(20);
            window.Close();
        }
    }
}
