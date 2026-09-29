using System.Security.Cryptography;
using System.Text.Json;
using SkiaSharp;

internal static class ReferenceImageAudit
{
    // Compare the actual approved PNG bytes/pixels, not a previous program build.
    // Runtime prices/results differ deliberately. No arbitrary similarity threshold
    // is promoted into a claim that the user's strict 100% requirement has passed.
    public static void Build(string captured, string referenceRoot)
    {
        var names = new Dictionary<string,string> {
            ["overview"]="Tab Tổng Quan.png", ["configuration"]="Tab Cấu Hình.png",
            ["strategy"]="Tab Chiến Lược.png", ["monitoring"]="Tab Giám Sát.png",
            ["orders"]="Tab Lệnh & Vị thế.png", ["backtest"]="Tab BackTest.png",
            ["optimization"]="Tab Tối Ưu.png", ["logs"]="Tab Nhật Kí.png",
            ["tools"]="Tab Công Cụ.png", ["settings"]="Tab Cài Đặt.png" };
        string destination = Path.Combine(captured,"reference-comparison");Directory.CreateDirectory(destination);
        var report=new List<object>();
        var html=new System.Text.StringBuilder("<!doctype html><html lang=vi><meta charset=utf-8><title>XAUPY RC2 — Reference review</title><style>body{font:16px system-ui;background:#061a2a;color:#eaf5ff;margin:24px}img{width:100%;height:auto;border:1px solid #31516a}section{margin:36px 0}p{max-width:1100px;line-height:1.6}a{color:#7ac4ff}</style><h1>Ảnh demo (trái) / control RC2 (phải)</h1><p>Ảnh phải là control thật với dữ liệu thử cách ly, không phải giao dịch MT5. So sánh trực tiếp tất cả 10 ảnh đã duyệt ở cùng kích thước. Chênh lệch dữ liệu động không được làm giả. Báo cáo này ghi nhận sai khác; không tự chứng nhận giao diện 100%.</p>");
        foreach(var entry in names)
        {
            string reference=Path.Combine(referenceRoot,entry.Value), actual=Path.Combine(captured,entry.Key+".png");
            if(!File.Exists(reference)||!File.Exists(actual))throw new InvalidDataException("Missing reference/candidate: "+entry.Key);
            using var left=SKBitmap.Decode(reference);using var right=SKBitmap.Decode(actual);
            if(left is null||right is null||left.Width!=right.Width||left.Height!=right.Height)
                throw new InvalidDataException("Reference dimensions differ: "+entry.Key);
            bool exact=left.Pixels.SequenceEqual(right.Pixels);
            using var joined=new SKBitmap(left.Width+right.Width,left.Height);
            using(var canvas=new SKCanvas(joined)){canvas.Clear(SKColors.Transparent);canvas.DrawBitmap(left,0,0);canvas.DrawBitmap(right,left.Width,0);}
            using var image=SKImage.FromBitmap(joined);using var data=image.Encode(SKEncodedImageFormat.Png,100);
            using(var stream=File.Create(Path.Combine(destination,entry.Key+"-pair.png")))data.SaveTo(stream);
            string Hash(string p)=>Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(p))).ToLowerInvariant();
            report.Add(new {page=entry.Key,reference=entry.Value,reference_sha256=Hash(reference),capture_sha256=Hash(actual),
                width=left.Width,height=left.Height,raw_pixel_identical=exact,acceptance="MANUAL_REFERENCE_REVIEW_REQUIRED"});
            html.Append($"<section><h2>{System.Net.WebUtility.HtmlEncode(entry.Value)}</h2><a href='{entry.Key}-pair.png'>Mở ảnh đầy đủ</a><img src='{entry.Key}-pair.png' loading=lazy></section>");
        }
        File.WriteAllText(Path.Combine(destination,"index.html"),html+"</html>");
        File.WriteAllText(Path.Combine(destination,"comparison.json"),JsonSerializer.Serialize(new {
            scope="APPROVED_PNG_VS_ACTUAL_HEADLESS_CONTROLS; NO MT5; NO AUTOMATIC_100_PERCENT_SIGNOFF",pages=report
        },new JsonSerializerOptions{WriteIndented=true}));
        Console.WriteLine("PASS produced all ten approved-reference/candidate pairs; strict parity remains a separate verdict.");
    }
}
