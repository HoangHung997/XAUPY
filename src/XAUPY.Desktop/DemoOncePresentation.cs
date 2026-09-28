using System.Globalization;
using Avalonia.Media;
using XAUPY.Ipc;

namespace XAUPY.Desktop;

internal static class DemoOncePresentation
{
    public static bool IsVisible(DemoOnceSnapshot report) => report.HasReport && report.State != "DISABLED";

    public static string StateLabel(DemoOnceSnapshot report) => !report.IsFresh ? "MẤT KẾT NỐI" : report.State switch
    {
        "ARMED" => "CHỜ TÍN HIỆU",
        "DISPATCHED" => "ĐÃ GỬI",
        "FILLED" => "ĐÃ KHỚP",
        "REJECTED" => "BỊ TỪ CHỐI",
        "CANCELLED" => "ĐÃ HỦY",
        "SUSPENDED" => "TẠM DỪNG",
        "EXPIRED" => "HẾT HẠN",
        _ => "CẦN KIỂM TRA"
    };

    public static IBrush StatusBrush(DemoOnceSnapshot report) => !report.IsFresh ? Brushes.Gold : report.State switch
    {
        "FILLED" => Brushes.MediumSpringGreen,
        "DISPATCHED" => Brushes.LightSkyBlue,
        "REJECTED" or "UNKNOWN" => Brushes.Salmon,
        _ => Brushes.Gold
    };

    public static string Summary(DemoOnceSnapshot report)
    {
        var parts = new List<string> { $"DEMO 1 LỆNH · {StateLabel(report)}" };
        if (!string.IsNullOrWhiteSpace(report.Side)) parts.Add(report.Side);
        if (report.Volume.HasValue) parts.Add($"{report.Volume.Value.ToString("0.########", CultureInfo.InvariantCulture)} lot");
        if (report.OrderTicket.HasValue) parts.Add($"Order #{report.OrderTicket}");
        if (report.DealTicket.HasValue) parts.Add($"Deal #{report.DealTicket}");
        return string.Join(" · ", parts);
    }

    public static string Detail(DemoOnceSnapshot report)
    {
        var parts = new List<string> { Summary(report), "Khóa giao dịch chung vẫn bật; nút đặt lệnh thủ công chỉ mô phỏng." };
        if (!report.IsFresh) parts.Add($"Trạng thái cuối được báo: {report.State}. Chưa xác nhận kết quả mới; cần kiểm tra MT5.");
        if (!string.IsNullOrWhiteSpace(report.AttemptId)) parts.Add($"Attempt: {report.AttemptId}");
        if (!string.IsNullOrWhiteSpace(report.Reason)) parts.Add(report.Reason);
        if (!string.IsNullOrWhiteSpace(report.Code)) parts.Add(report.Code);
        return string.Join(Environment.NewLine, parts);
    }
}
