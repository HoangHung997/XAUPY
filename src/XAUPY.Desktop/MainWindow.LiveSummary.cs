using System.Text.Json;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Media;
using XAUPY.Ipc;

namespace XAUPY.Desktop;

public partial class MainWindow
{
    private void ApplyLiveSummary(JsonElement? monitoring, OrdersPositionsSnapshot book)
    {
        string Metric(string key,string format) => monitoring is { } report && report.TryGetProperty("kpi",out var kpi) &&
            kpi.TryGetProperty(key,out var value) && value.ValueKind==JsonValueKind.Number && value.TryGetDouble(out double number) ? number.ToString(format) : "—";
        FindText("DailyProfitValue").Text = Metric("profit_today","+0.00;-0.00;0.00");
        FindText("DailyTradeCountValue").Text = Metric("trades_today","0");
        FindText("DailyDrawdownValue").Text = Metric("max_drawdown_pct","0.00")+"%";
        ToolTip.SetTip(FindText("DailyDrawdownValue"), "Drawdown của chiến lược từ các mẫu equity app đã quan sát trong ngày broker; lưu qua lần mở app. Không suy diễn giá trong thời gian app chưa chạy.");
        var host = this.FindControl<StackPanel>("RecentOrdersRows")!;
        host.Children.Clear();
        var rows = new List<(long Time,string[] Cells,double Pnl)>();
        foreach(var position in book.Positions.Where(p=>p.Symbol==book.Symbol))
            rows.Add((position.Time,[position.Ticket.ToString(),Clock(position.Time),position.Side,position.Volume.ToString("0.###"),position.PriceOpen.ToString("0.00###"),"Đang mở",
                position.Profit.ToString("+0.00;-0.00;0.00"),position.Tp>0?position.Tp.ToString("0.00###"):"—",position.Sl>0?position.Sl.ToString("0.00###"):"—"],position.Profit));
        foreach(var deal in book.Deals.Where(d=>d.Symbol==book.Symbol))
            rows.Add((deal.Time,[deal.Ticket.ToString(),Clock(deal.Time),deal.Side,deal.Volume.ToString("0.###"),deal.PriceIn>0?deal.PriceIn.ToString("0.00###"):"—",deal.PriceOut.ToString("0.00###"),
                deal.RealizedTotal.ToString("+0.00;-0.00;0.00"),deal.Tp>0?deal.Tp.ToString("0.00###"):"—",deal.Sl>0?deal.Sl.ToString("0.00###"):"—"],deal.RealizedTotal));
        foreach(var row in rows.OrderByDescending(r=>r.Time).Take(8))
        {
            var grid = new Grid { ColumnDefinitions=new ColumnDefinitions("0.5*,1.3*,0.8*,0.7*,1*,1*,0.8*,0.8*,0.8*"),Margin=new Thickness(12,2) };
            for(int i=0;i<row.Cells.Length;i++)
            {
                var cell=new TextBlock { Text=row.Cells[i],FontSize=12,TextTrimming=TextTrimming.CharacterEllipsis,
                    Foreground=i==6 ? row.Pnl>=0 ? Brushes.SpringGreen : Brushes.IndianRed : Brushes.LightGray };
                ToolTip.SetTip(cell,row.Cells[i]);Grid.SetColumn(cell,i);grid.Children.Add(cell);
            }
            host.Children.Add(grid);
        }
        FindText("RecentOrdersEmptyText").IsVisible = rows.Count==0;
        FindText("RecentOrdersEmptyText").Text = book.Available ? "Chưa có vị thế hoặc giao dịch của chiến lược." : "Chờ dữ liệu giao dịch từ MT5.";
        static string Clock(long stamp) => stamp>0 ? DateTimeOffset.FromUnixTimeSeconds(stamp).ToString("dd/MM HH:mm") : "—";
    }
}
