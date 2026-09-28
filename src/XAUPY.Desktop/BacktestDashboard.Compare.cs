using System.Globalization;
using System.Net;
using System.Text;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Platform.Storage;
using XAUPY.Ipc;

namespace XAUPY.Desktop;

public partial class BacktestDashboard
{
    private async void CompareResults_OnClick(object? sender,RoutedEventArgs e)
    {
        if(_supervisor is null || TopLevel.GetTopLevel(this) is not Window owner)return;
        try
        {
            await EnsureLoadedAsync(true);
            if(_history.Count<2)throw new InvalidOperationException("Cần ít nhất hai kết quả Backtest đã lưu.");
            var runs=_history.ToArray();
            string Label(BacktestHistoryItem r)=>$"{r.CreatedAtUtc} · {r.Symbol} · {r.FromDate}–{r.ToDate} · P/L {r.Metrics.NetProfit:0.00} · {ShortHash(r.ProfileHash)}";
            var left=new ComboBox {ItemsSource=runs.Select(Label).ToArray(),SelectedIndex=0,HorizontalAlignment=HorizontalAlignment.Stretch};
            var right=new ComboBox {ItemsSource=runs.Select(Label).ToArray(),SelectedIndex=1,HorizontalAlignment=HorizontalAlignment.Stretch};
            var body=new TextBox {IsReadOnly=true,AcceptsReturn=true,FontFamily="Consolas",TextWrapping=TextWrapping.NoWrap,MinHeight=285};
            var compare=new Button {[LocalizationService.TextProperty] = "So sánh"}; var export=new Button {[LocalizationService.TextProperty] = "Xuất báo cáo HTML",IsEnabled=false};
            string html="";
            async Task RenderComparison()
            {
                if(left.SelectedIndex<0 || right.SelectedIndex<0 || left.SelectedIndex==right.SelectedIndex){body.Text="Chọn hai lần chạy khác nhau.";export.IsEnabled=false;return;}
                var a=runs[left.SelectedIndex];var b=runs[right.SelectedIndex];
                var fullA=await _supervisor.GetBacktestResultAsync(a.RunId,tradeLimit:1);
                var fullB=await _supervisor.GetBacktestResultAsync(b.RunId,tradeLimit:1);
                if(left.SelectedIndex<0 || right.SelectedIndex<0 || runs[left.SelectedIndex].RunId!=a.RunId || runs[right.SelectedIndex].RunId!=b.RunId)return;
                bool comparable=a.DatasetFingerprint==b.DatasetFingerprint && a.FromDate==b.FromDate && a.ToDate==b.ToDate && a.Model==b.Model &&
                    fullA.InitialBalance==fullB.InitialBalance && fullA.SpreadPips==fullB.SpreadPips && fullA.CommissionPerLot==fullB.CommissionPerLot;
                var rows=new List<(string Label,string A,string B,string Delta)> {
                    ("Run",a.RunId,b.RunId,""),("Model",a.Model,b.Model,""),("Dataset",a.DatasetFileName,b.DatasetFileName,""),
                    ("Dataset SHA",a.DatasetFingerprint,b.DatasetFingerprint,""),("Profile SHA",a.ProfileHash,b.ProfileHash,""),
                    ("Khoảng ngày",a.FromDate+" – "+a.ToDate,b.FromDate+" – "+b.ToDate,""),
                    ("Vốn đầu",fullA.InitialBalance.ToString(),fullB.InitialBalance.ToString(),""),
                    ("Spread giả định (points)",fullA.SpreadPips.ToString(),fullB.SpreadPips.ToString(),""),
                    ("Phí khứ hồi / lot",fullA.CommissionPerLot.ToString(),fullB.CommissionPerLot.ToString(),"")};
                foreach(var p in typeof(BacktestMetrics).GetProperties())
                {
                    object? av=p.GetValue(a.Metrics),bv=p.GetValue(b.Metrics);
                    string Format(object? v)=>v is null?"—":Convert.ToDouble(v).ToString("0.####",CultureInfo.InvariantCulture);
                    rows.Add((p.Name,Format(av),Format(bv),av is null || bv is null?"—":(Convert.ToDouble(bv)-Convert.ToDouble(av)).ToString("+0.####;-0.####;0",CultureInfo.InvariantCulture)));
                }
                string note=comparable?"Cùng dữ liệu, khoảng ngày, model, vốn và chi phí. Tick dùng spread Bid/Ask quan sát; cần xét thêm mức rủi ro của mỗi profile.":"Hai lần chạy khác dữ liệu, khoảng ngày, model, vốn hoặc chi phí; mức lợi nhuận không phải phép so sánh cùng điều kiện.";
                body.Text=note+"\n\n"+string.Join("\n",rows.Select(r=>$"{r.Label,-24} {r.A} | {r.B} | Δ {r.Delta}"));
                string E(string s)=>WebUtility.HtmlEncode(s);
                html="<!doctype html><html lang=vi><meta charset=utf-8><title>XAUPY • So sánh Backtest</title><style>body{font:15px system-ui;background:#071827;color:#ddecf8;padding:32px}table{border-collapse:collapse;width:100%}td,th{padding:10px;border:1px solid #31516a;text-align:left;overflow-wrap:anywhere}p{color:#ffd36a}</style><h1>So sánh Backtest XAUPY</h1><p>"+E(note)+"</p><table><tr><th>Chỉ tiêu</th><th>A</th><th>B</th><th>B − A</th></tr>"+string.Join("",rows.Select(r=>$"<tr><td>{E(r.Label)}</td><td>{E(r.A)}</td><td>{E(r.B)}</td><td>{E(r.Delta)}</td></tr>"))+"</table></html>";
                export.IsEnabled=true;
            }
            compare.Click+=async (_,_)=>{try{compare.IsEnabled=false;await RenderComparison();}catch(Exception ex){body.Text=ex.Message;export.IsEnabled=false;}finally{compare.IsEnabled=true;}};
            left.SelectionChanged+=(_,_)=>{export.IsEnabled=false;}; right.SelectionChanged+=(_,_)=>{export.IsEnabled=false;};
            var dialog=new Window {Title="So sánh kết quả Backtest",Width=1060,Height=630,WindowStartupLocation=WindowStartupLocation.CenterOwner};
            export.Click+=async (_,_)=>
            {
                try
                {
                    var file=await dialog.StorageProvider.SaveFilePickerAsync(new FilePickerSaveOptions {Title="Lưu so sánh",SuggestedFileName="XAUPY-backtest-comparison.html",DefaultExtension="html"});
                    if(file is null)return;await using var stream=await file.OpenWriteAsync();if(stream.CanSeek)stream.SetLength(0);
                    await using var writer=new StreamWriter(stream,new UTF8Encoding(false));await writer.WriteAsync(html);
                }catch(Exception ex){body.Text=ex.Message;}
            };
            dialog.Content=new StackPanel {Margin=new Thickness(18),Spacing=12,Children={new TextBlock {Text="A"},left,new TextBlock {Text="B"},right,new StackPanel {Orientation=Orientation.Horizontal,Spacing=10,Children={compare,export}},new ScrollViewer {Content=body,MaxHeight=370}}};
            await RenderComparison();await dialog.ShowDialog(owner);
        }
        catch(Exception ex){SetStatus(ex.Message,Brushes.IndianRed);}
    }
}
