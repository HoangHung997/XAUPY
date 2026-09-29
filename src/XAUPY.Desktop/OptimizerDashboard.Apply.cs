using System.Text.Json;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Platform.Storage;
using XAUPY.Ipc;

namespace XAUPY.Desktop;

public partial class OptimizerDashboard
{
    public Func<bool>? HasConflictingDraft {get;set;}
    private async Task ShowCandidateAsync(OptimizerCandidateSnapshot selected)
    {
        if(_supervisor is null || _currentSweep is null || TopLevel.GetTopLevel(this) is not Window owner)return;
        var response=await _supervisor.PrepareOptimizerCandidateAsync(_currentSweep.RunId,selected.Index);
        if(!response.GetProperty("ok").GetBoolean())throw new InvalidDataException(response.GetProperty("errors").ToString());
        var candidate=response.GetProperty("candidate");
        bool contextMatches = !candidate.TryGetProperty("analysis_context_matches",out var context) || context.GetBoolean();
        var profile=candidate.GetProperty("profile");var baseline=candidate.GetProperty("expected_profile");
        string json=JsonSerializer.Serialize(profile,new JsonSerializerOptions {WriteIndented=true});
        var status=new TextBlock {[LocalizationService.TextProperty] = "Xếp hạng trên mẫu đã chạy; chưa phải bằng chứng ngoài mẫu. Chỉ các tham số bên dưới được thay đổi. Quyền giao dịch giữ theo lựa chọn hiện tại.",TextWrapping=TextWrapping.Wrap,Foreground=Brushes.Gold};
        if(candidate.TryGetProperty("research",out var evidence) && evidence.ValueKind==JsonValueKind.Object)
            status.Text=(candidate.GetProperty("qualified").GetBoolean()?"Ứng viên đạt các điều kiện kiểm tra lịch sử.":"Ứng viên chưa đạt đầy đủ điều kiện nghiên cứu.")+" Đây là dữ liệu quá khứ được sử dụng lại; cần kiểm tra tiến tới. Quyền và rủi ro giữ theo cấu hình hiện tại.";
        if(!contextMatches)
            status.Text += "\nCấu hình hiện tại khác điều kiện đã kiểm: " + string.Join(", ",candidate.GetProperty("context_changes").EnumerateArray().Select(c=>c.GetProperty("path").GetString())) + ". Cần chạy lại nghiên cứu để đánh giá bộ kết hợp này.";
        string changes=string.Join("\n",candidate.GetProperty("changes").EnumerateArray().Select(c=>$"{c.GetProperty("path")}: {c.GetProperty("before")} → {c.GetProperty("after")}"));
        string metrics=$"P/L {selected.Metrics.NetProfit:0.00} • {selected.Metrics.TotalTrades} lệnh • DD {selected.Metrics.MaxDrawdownPct:0.00}%";
        var apply=new Button {[LocalizationService.TextProperty] = "Áp dụng các thay đổi này"};var export=new Button {[LocalizationService.TextProperty] = "Xuất profile JSON"};
        var dialog=new Window {Title=$"Ứng viên #{selected.Rank} • Kiểm tra trước khi áp dụng",Width=780,Height=600,WindowStartupLocation=WindowStartupLocation.CenterOwner};
        var confirmation=new CheckBox {[LocalizationService.TextProperty] = "Tôi chọn áp dụng bộ tham số đã xem vào cấu hình đang dùng"};
        apply.IsEnabled=false;confirmation.IsCheckedChanged+=(_,_)=>apply.IsEnabled=confirmation.IsChecked==true;
        apply.Click+=async (_,_)=>
        {
            try
            {
                apply.IsEnabled=false;
                if(HasConflictingDraft?.Invoke()==true)throw new InvalidOperationException("Có bản nháp chưa áp dụng ở tab khác. Lưu hoặc hủy bản nháp trước khi thay cấu hình.");
                var applied=await _supervisor.ApplyActiveConfigAsync(profile,expectedProfile:baseline);
                if(!applied.Applied)throw new InvalidDataException(string.Join(" • ",applied.Errors));
                SetStateMessage("Đã áp dụng bộ tham số người dùng chọn. Quyền tài khoản và chế độ giao dịch giữ nguyên.",Brushes.LightGreen);
                dialog.Close();
            }
            catch(Exception ex){status.Text=ex.Message;status.Foreground=Brushes.IndianRed;confirmation.IsChecked=false;}
        };
        export.Click+=async (_,_)=>
        {
            try
            {
                var file=await dialog.StorageProvider.SaveFilePickerAsync(new FilePickerSaveOptions {Title="Xuất cấu hình ứng viên",SuggestedFileName=$"XAUPY-candidate-{selected.Index}.json",DefaultExtension="json"});
                if(file is null)return;await FileOutput.WriteTextAsync(file,json);status.Text="Đã xuất cấu hình; bản đang chạy chưa đổi.";
            }catch(Exception ex){status.Text=ex.Message;}
        };
        dialog.Content=new Grid {RowDefinitions=new RowDefinitions("Auto,Auto,*,Auto,Auto"),Margin=new Thickness(18),RowSpacing=12};
        var grid=(Grid)dialog.Content;
        grid.Children.Add(status);var metricText=new TextBlock {Text=metrics};Grid.SetRow(metricText,1);grid.Children.Add(metricText);
        var detail=new TextBox {Text=changes,IsReadOnly=true,AcceptsReturn=true,TextWrapping=TextWrapping.Wrap};Grid.SetRow(detail,2);grid.Children.Add(detail);
        Grid.SetRow(confirmation,3);grid.Children.Add(confirmation);
        var actions=new StackPanel {Orientation=Orientation.Horizontal,Spacing=12,Children={apply,export}};Grid.SetRow(actions,4);grid.Children.Add(actions);
        await dialog.ShowDialog(owner);
    }

    private async void ResearchReport_OnClick(object? sender,Avalonia.Interactivity.RoutedEventArgs e)
    {
        try
        {
            if(_supervisor is null || _currentSweep?.Mode!="RESEARCH" || TopLevel.GetTopLevel(this) is not Window owner)return;
            var response=await _supervisor.GetOptimizerEvidenceAsync(_currentSweep.RunId);
            if(!response.GetProperty("ok").GetBoolean())throw new InvalidDataException(response.ToString());
            var result=response.GetProperty("result");var research=result.GetProperty("research");
            var lines=new List<string> {research.GetProperty("qualified").GetBoolean()?"CÓ ỨNG VIÊN ĐẠT ĐIỀU KIỆN LỊCH SỬ":"KHÔNG CÓ ỨNG VIÊN ĐẠT ĐỦ ĐIỀU KIỆN",
                $"Nguồn: {_currentSweep.DatasetFileName} • {_currentSweep.BacktestModel}",
                $"Ứng viên đã chọn trước kiểm tra: #{research.GetProperty("selected_index")}",
                "Mỗi giai đoạn: lãi ròng dương, đủ số lệnh tối thiểu, sụt giảm ≤20%, không lỗi mô hình.",
                "Dữ liệu quá khứ có thể đã được xem trước. Không thay thế kiểm tra tiến tới.",""};
            foreach(var stage in research.GetProperty("stages").EnumerateObject())
            {
                var m=stage.Value.GetProperty("metrics");
                lines.Add($"{stage.Name}: {m.GetProperty("total_trades")} lệnh | Net {m.GetProperty("net_profit")} | DD {m.GetProperty("max_drawdown_pct")}%");
                if(stage.Value.TryGetProperty("rejection_reason",out var reason) && reason.ValueKind==JsonValueKind.String)lines.Add(reason.GetString()!);
            }
            lines.Add("\nChi phí thử: phí ×1,5, trượt giá ×2. Spread tick giữ quan sát thực; OHLC ×1,5.");
            lines.Add("Chưa mô hình hóa swap, thanh khoản và độ trễ broker. Chỉ áp dụng qua nút Xem của ứng viên.");
            var dialog=new Window {Title="Báo cáo nghiên cứu RSI / Z",Width=850,Height=580,WindowStartupLocation=WindowStartupLocation.CenterOwner};
            var save=new Button {[LocalizationService.TextProperty] = "Xuất toàn bộ bằng chứng JSON"};
            var status=new TextBlock {TextWrapping=TextWrapping.Wrap};
            save.Click+=async (_,_)=> {try {
                var file=await dialog.StorageProvider.SaveFilePickerAsync(new FilePickerSaveOptions {SuggestedFileName="XAUPY-research.json",DefaultExtension="json"});
                if(file is null)return;await FileOutput.WriteTextAsync(file,JsonSerializer.Serialize(result,new JsonSerializerOptions {WriteIndented=true}));status.Text="Đã xuất báo cáo.";
            }catch(Exception ex){status.Text=ex.Message;}};
            var panel=new DockPanel {Margin=new Thickness(16)};DockPanel.SetDock(save,Dock.Bottom);panel.Children.Add(save);DockPanel.SetDock(status,Dock.Bottom);panel.Children.Add(status);
            panel.Children.Add(new TextBox {Text=string.Join("\n",lines),IsReadOnly=true,AcceptsReturn=true,TextWrapping=TextWrapping.Wrap});dialog.Content=panel;await dialog.ShowDialog(owner);
        }catch(Exception ex){SetStateMessage(ex.Message,Brushes.IndianRed);}
    }
}
