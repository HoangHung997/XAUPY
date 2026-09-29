using System.Text.Json;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Layout;
using Avalonia.Platform.Storage;

namespace XAUPY.Desktop;

public partial class ToolsDashboard
{
    private async void ClearStartup_OnClick(object? sender,RoutedEventArgs e) => await RunAsync(async ()=>
    {
        if(_supervisor is null)return;
        var result=await _supervisor.ClearStartupProfileAsync();EnsureOk(result);
        Result("Đã bỏ hồ sơ khởi động riêng. Lần mở sau dùng cấu hình đã lưu gần nhất; bản đang chạy không đổi.",true);
    });
    private async void SaveLibrary_OnClick(object? sender,RoutedEventArgs e) => await RunAsync(async ()=>
    {
        if (_supervisor is null) return;
        using var doc=JsonDocument.Parse(ToolEditor.Text ?? "");
        var response=await _supervisor.SaveLibraryProfileAsync(LibraryProfileId.Text ?? "",doc.RootElement);
        EnsureOk(response);
        Result($"Đã lưu phiên bản {response.GetProperty("saved").GetProperty("revision").GetString()![..12]} trong thư viện. Bản đang chạy chỉ đổi khi Áp dụng.",true);
    });
    private async void OpenLibrary_OnClick(object? sender,RoutedEventArgs e) => await RunAsync(async ()=>
    {
        if(_supervisor is null || TopLevel.GetTopLevel(this) is not Window owner || !await ConfirmDiscardDraftAsync()) return;
        var response=await _supervisor.QueryProfileLibraryAsync(); EnsureOk(response);
        var entries=response.GetProperty("profiles").EnumerateArray().Select(v=>v.Clone()).ToArray();
        var list=new ListBox { ItemsSource=entries.Select(v=>$"{v.GetProperty("id")} • {v.GetProperty("name")} • {v.GetProperty("saved_utc")} • {v.GetProperty("revision").GetString()![..12]}").ToArray(),MinHeight=240 };
        var open=new Button { [LocalizationService.TextProperty] = "Nạp vào bản nháp" };
        var dialog=new Window { [LocalizationService.TitleProperty] = "Thư viện hồ sơ và phiên bản",Width=820,Height=420,WindowStartupLocation=WindowStartupLocation.CenterOwner };
        int selected=-1;
        open.Click+=(_,_)=>{ if(list.SelectedIndex>=0){selected=list.SelectedIndex;dialog.Close();} };
        dialog.Content=new StackPanel { Margin=new Thickness(16),Spacing=10,Children={new TextBlock { [LocalizationService.TextProperty] = "Mỗi lần lưu giữ một phiên bản. Nạp bản nháp để kiểm tra trước khi áp dụng." },new ScrollViewer { Content=list,MaxHeight=280 },open} };
        await dialog.ShowDialog(owner);
        if(selected<0) return;
        var entry=entries[selected];
        var profile=await _supervisor.GetLibraryProfileAsync(entry.GetProperty("id").GetString()!,entry.GetProperty("revision").GetString()!); EnsureOk(profile);
        LibraryProfileId.Text=entry.GetProperty("id").GetString();
        _currentFile=null;
        ToolEditor.Text=JsonSerializer.Serialize(profile.GetProperty("profile"),Pretty);
        Result("Đã nạp phiên bản vào bản nháp. Nhấn Áp dụng khi muốn sử dụng.",true);
    });
    private async void CompareFiles_OnClick(object? sender,RoutedEventArgs e) => await RunAsync(async ()=>
    {
        var storage=TopLevel.GetTopLevel(this)?.StorageProvider;
        if(storage is null || !await ConfirmDiscardDraftAsync()) return;
        var files=await storage.OpenFilePickerAsync(new FilePickerOpenOptions { Title = LocalizationService.T("Chọn đúng hai preset JSON"),AllowMultiple=true,FileTypeFilter=new[]{JsonType} });
        if(files.Count==0) return;
        if(files.Count!=2) throw new InvalidDataException("Chọn đúng hai file để so sánh.");
        async Task<JsonElement> Read(IStorageFile file)
        {
            await using var stream=await file.OpenReadAsync();
            if(stream.CanSeek && stream.Length>2*1024*1024) throw new InvalidDataException("Preset vượt quá 2 MiB.");
            using var doc=await JsonDocument.ParseAsync(stream); return doc.RootElement.Clone();
        }
        var left=await Read(files[0]); var right=await Read(files[1]);
        var differences=new List<object>(); CompareAll("",left,right,differences);
        PresentReadOnlyReport("compare", JsonSerializer.Serialize(new { baseline=files[0].Name,candidate=files[1].Name,differences },Pretty));
        Result($"{differences.Count} khác biệt giữa hai preset.",true);
    });
    private static void CompareAll(string path,JsonElement left,JsonElement right,List<object> rows)
    {
        if(left.ValueKind==JsonValueKind.Object && right.ValueKind==JsonValueKind.Object)
        {
            foreach(var name in left.EnumerateObject().Select(v=>v.Name).Union(right.EnumerateObject().Select(v=>v.Name)).Order())
            {
                bool a=left.TryGetProperty(name,out var l), b=right.TryGetProperty(name,out var r);
                string field=path.Length==0?name:path+"."+name;
                if(a && b) CompareAll(field,l,r,rows);
                else rows.Add(new { path=field,baseline=a?l.ToString():null,candidate=b?r.ToString():null });
            }
        }
        else if(left.ToString()!=right.ToString() || left.ValueKind!=right.ValueKind) rows.Add(new {path,baseline=left.Clone(),candidate=right.Clone()});
    }
}
