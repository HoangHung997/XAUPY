using System.Text.Json;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Platform.Storage;

namespace XAUPY.Desktop;

public partial class ToolsDashboard
{
    private async void DataTransfer_OnClick(object? sender,RoutedEventArgs e) => await RunAsync(async ()=>
    {
        if(_supervisor is null || TopLevel.GetTopLevel(this) is not {} top)return;
        var type=new FilePickerFileType("XAUPY data bundle") {Patterns=["*.zip"]};
        string mode=(sender as Button)?.Tag?.ToString() ?? "EXPORT";
        string? path;
        if(mode=="EXPORT")
        {
            var file=await top.StorageProvider.SaveFilePickerAsync(new FilePickerSaveOptions {Title = LocalizationService.T("Xuất dữ liệu phân tích và nhật ký"),SuggestedFileName=$"XAUPY-data-{DateTime.Now:yyyyMMdd-HHmmss}.zip",DefaultExtension="zip",FileTypeChoices=[type]});
            path=file?.TryGetLocalPath();
        }
        else
        {
            var files=await top.StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions {Title = LocalizationService.T("Nhập gói XAUPY đã xuất"),AllowMultiple=false,FileTypeFilter=[type]});
            path=files.FirstOrDefault()?.TryGetLocalPath();
        }
        if(path is null)return;
        var response=await _supervisor.StartDataTransferAsync(mode,path);ShowTransfer(response);
    });
    private async void DataTransferStatus_OnClick(object? sender,RoutedEventArgs e) => await RunAsync(async ()=>
    {if(_supervisor is not null)ShowTransfer(await _supervisor.GetDataTransferAsync());});
    private async void DataTransferCancel_OnClick(object? sender,RoutedEventArgs e) => await RunAsync(async ()=>
    {if(_supervisor is not null)ShowTransfer(await _supervisor.CancelDataTransferAsync());});
    private void ShowTransfer(JsonElement response)
    {
        EnsureOk(response);var transfer=response.GetProperty("transfer");
        ToolEditor.Text=JsonSerializer.Serialize(transfer,Pretty);_loadedText=ToolEditor.Text;
        Result($"Gói dữ liệu: {transfer.GetProperty("status")}. Chọn Tiến độ gói để cập nhật. Nhập dữ liệu không áp dụng profile, lịch tin hay quyền giao dịch; nhật ký nằm trong thư mục import.",transfer.GetProperty("status").GetString()!="FAILED");
    }
}
