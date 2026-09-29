using System.Text.Json;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Layout;
using Avalonia.Platform.Storage;
using XAUPY.Ipc;

namespace XAUPY.Desktop;

internal static class HistoryDatasetPicker
{
    public static async Task<string?> PickAsync(Control parent,EngineProcessSupervisor supervisor)
    {
        if(TopLevel.GetTopLevel(parent) is not Window owner) return null;
        var response=await supervisor.QueryHistoryCatalogAsync();
        if(!response.GetProperty("ok").GetBoolean()) throw new InvalidDataException(response.GetProperty("errors").ToString());
        var entries=response.GetProperty("datasets").EnumerateArray().Where(e=>e.GetProperty("timeframe").GetString() is "M1" or "TICKS").Select(e=>e.Clone()).ToArray();
        bool filePicker=entries.Length==0;
        string? selected=null;
        if(entries.Length>0)
        {
            var list=new ListBox { ItemsSource=entries.Select(e=>$"{e.GetProperty("symbol")} • {e.GetProperty("timeframe")} • {e.GetProperty("rows")} quan sát • {e.GetProperty("broker_server")} • {e.GetProperty("id")}").ToArray(),SelectedIndex=0 };
            var use=new Button { [LocalizationService.TextProperty] = "Dùng kho đã tải" }; var file=new Button { [LocalizationService.TextProperty] = "Chọn file khác…" };
            var dialog=new Window { [LocalizationService.TitleProperty] = "Chọn dữ liệu lịch sử",Width=810,Height=390,WindowStartupLocation=WindowStartupLocation.CenterOwner };
            use.Click+=(_,_)=>{ if(list.SelectedIndex>=0) { selected=entries[list.SelectedIndex].GetProperty("path").GetString(); dialog.Close(); } };
            file.Click+=(_,_)=>{filePicker=true;dialog.Close();};
            dialog.Content=new StackPanel { Margin=new Thickness(16),Spacing=12,Children={new TextBlock { [LocalizationService.TextProperty] = "Kho lịch sử MT5 • nến đóng và tick Bid/Ask thực tế" },new ScrollViewer {Content=list,Height=260},new StackPanel {Orientation=Orientation.Horizontal,Spacing=10,Children={use,file}}} };
            await dialog.ShowDialog(owner);
        }
        if(filePicker)
        {
            var files=await owner.StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions {Title = LocalizationService.T("Chọn dữ liệu lịch sử M1"),AllowMultiple=false,FileTypeFilter=new[]{new FilePickerFileType("Lịch sử JSON/CSV"){Patterns=new[]{"*.json","*.csv"}}} });
            selected=files.FirstOrDefault()?.Path.LocalPath;
        }
        return selected;
    }
}
