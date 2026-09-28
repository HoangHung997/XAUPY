using System.Text.Json;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Layout;
using Avalonia.Media;
using XAUPY.Ipc;

namespace XAUPY.Desktop;

public partial class MonitoringDashboard
{
    private bool _servicesSeen;
    public void ApplyServices(JsonElement? data, ExecutionSnapshot execution)
    {
        // IPC availability and broker market-data availability are independent.
        Text("MonitorEngineDot").Foreground = execution.Fresh ? Brushes.MediumSpringGreen : Brushes.Gold;
        Text("MonitorSnapshotCountText").Text = LocalizationService.T(execution.Fresh ? "Đang chạy" : "Mất kết nối");
        Text("ExecutionMode").Text = execution.Label;
        Text("ExecutionReason").Text = execution.Reason;
        if (data is not { } report)
        {
            _servicesSeen = false;
            foreach (string name in new[] { "CpuPercent", "RamPercent", "DiskPercent", "MonitorAgeText", "ExecutionTotal", "ExecutionConfirmed", "ExecutionRejected", "ExecutionPending" }) Text(name).Text = "—";
            return;
        }
        _servicesSeen = true;
        if (report.TryGetProperty("resources", out var resources))
        {
            Text("CpuPercent").Text = Number(resources,"cpu_percent","0") + "%";
            Text("RamPercent").Text = Number(resources,"ram_percent","0") + "%";
            Text("DiskPercent").Text = Number(resources,"disk_percent","0") + "%";
            Text("ResourceDetail").Text = "Đĩa: dung lượng đã dùng · " + (resources.TryGetProperty("disk_path",out var disk) ? disk.ToString() : "—");
        }
        Text("MonitorAgeText").Text = Number(report,"broker_ping_ms","0.0");
        ToolTip.SetTip(Text("MonitorAgeText"), "Độ trễ MT5 ↔ broker do terminal đo (ms). Tuổi bản tin hiển thị riêng trong chẩn đoán.");
        if (report.TryGetProperty("sessions",out var sessions))
            foreach (var session in sessions.EnumerateArray())
            {
                string name = session.GetProperty("name").ToString().Replace(" ","")+"Session";
                bool available = session.TryGetProperty("available",out var ok) && ok.ValueKind == JsonValueKind.True;
                bool active = session.TryGetProperty("active",out var open) && open.ValueKind == JsonValueKind.True;
                Text(name).Text = available ? $"{(active ? "Mở" : "Đóng")} · {Number(session,"minutes_to_change","0")}p" : "—";
                Text(name).Foreground = active ? Brushes.SpringGreen : Brushes.SlateGray;
                ToolTip.SetTip(Text(name), "Phiên Forex tham khảo, có điều chỉnh giờ mùa hè. Giờ giao dịch symbol theo broker.");
            }
        if (report.TryGetProperty("calendar",out var calendar))
        {
            bool available = calendar.TryGetProperty("available",out var ok) && ok.ValueKind == JsonValueKind.True;
            long now = report.TryGetProperty("server_time",out var timestamp) && timestamp.ValueKind == JsonValueKind.Number && timestamp.TryGetInt64(out var parsed) ? parsed : 0;
            var rows = calendar.TryGetProperty("events",out var events)
                ? events.EnumerateArray().Where(ev => ev.GetProperty("time").GetInt64()/86400 == now/86400)
                    .OrderBy(ev => ev.GetProperty("time").GetInt64()).Select(ev =>
                        $"{DateTimeOffset.FromUnixTimeSeconds(ev.GetProperty("time").GetInt64()):HH:mm} {ev.GetProperty("currency")} · {ev.GetProperty("importance")} · {ev.GetProperty("name")}").ToArray()
                : [];
            Text("CalendarEventsText").Text = !available ? "Lịch MT5 chưa sẵn sàng: " + (calendar.TryGetProperty("reason",out var why) ? why.ToString() : "Chờ dữ liệu")
                : rows.Length > 0 ? string.Join('\n',rows) : "MT5 không có sự kiện cho symbol hôm nay.";
            ToolTip.SetTip(Text("CalendarEventsText"), "Giờ máy chủ MT5. Bộ lọc tin dùng cùng dữ liệu này.");
        }
        if (report.TryGetProperty("execution",out var state) && state.TryGetProperty("counts_today",out var counts))
        {
            int Count(string key) => counts.TryGetProperty(key,out var count) ? count.GetInt32() : 0;
            Text("ExecutionTotal").Text = counts.EnumerateObject().Sum(p => p.Value.GetInt32()).ToString();
            Text("ExecutionConfirmed").Text = Count("CONFIRMED").ToString();
            Text("ExecutionRejected").Text = Count("REJECTED").ToString();
            Text("ExecutionPending").Text = (Count("QUEUED")+Count("DISPATCHED")+Count("UNKNOWN")).ToString();
        }
        if (report.TryGetProperty("alerts",out var alerts) && alerts.GetArrayLength()>0)
        {
            Text("MonitorAlertText").Text = alerts[0].GetProperty("message").ToString();
            ToolTip.SetTip(Text("MonitorAlertText"), string.Join('\n',alerts.EnumerateArray().Select(a => $"{a.GetProperty("timestamp_utc")} · {a.GetProperty("message")}")));
        }
        if (report.TryGetProperty("scanner",out var scan)) RenderScanner(scan);
    }

    private void RenderScanner(JsonElement rows)
    {
        var table = this.FindControl<Grid>("MonitorConditionMatrix")!;
        table.Children.Clear(); table.RowDefinitions.Clear();
        table.RowDefinitions.Add(new RowDefinition(32,GridUnitType.Pixel));
        string[] headers = ["Khung", "Direction", "Pullback", "Trigger", "Trạng thái"];
        for(int i=0;i<headers.Length;i++) Cell(0,i,headers[i],true);
        int row=1;
        foreach(var scan in rows.EnumerateArray())
        {
            table.RowDefinitions.Add(new RowDefinition(33,GridUnitType.Pixel));
            var indicators=scan.GetProperty("indicators");
            Cell(row,0,scan.GetProperty("timeframe").ToString());
            Cell(row,1,scan.GetProperty("direction").ToString());
            Cell(row,2,indicators.TryGetProperty("pullback",out var pb) ? "Z "+Number(pb,"z","0.00") : "—");
            Cell(row,3,indicators.TryGetProperty("trigger",out var trigger) ? "RSI "+Number(trigger,"rsi","0.0") : "—");
            Cell(row,4,scan.GetProperty("state").ToString()); row++;
        }
        ToolTip.SetTip(table,"Quét từng khung độc lập từ nến đóng theo cùng cấu hình. Quyết định đặt lệnh dùng ba khung đã chọn trong chiến lược.");
        void Cell(int row,int column,string value,bool header=false)
        {
            var cell=new Border { BorderBrush=new SolidColorBrush(Color.Parse("#113A58")),BorderThickness=new Thickness(0,0,1,1),
                Padding=new Thickness(6,2),Child=new TextBlock { Text=value,FontSize=12,Foreground=header ? Brushes.LightSkyBlue : Brushes.LightGray,
                TextTrimming=TextTrimming.CharacterEllipsis,VerticalAlignment=VerticalAlignment.Center } };
            Grid.SetRow(cell,row);Grid.SetColumn(cell,column);table.Children.Add(cell);
        }
    }

    private static string Number(JsonElement parent,string key,string format) => parent.TryGetProperty(key,out var value) && value.ValueKind == JsonValueKind.Number && value.TryGetDouble(out double number) ? number.ToString(format) : "—";
}
