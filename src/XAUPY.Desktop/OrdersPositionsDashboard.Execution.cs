using System.Text.Json;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Layout;
using Avalonia.Media;
using XAUPY.Ipc;

namespace XAUPY.Desktop;

public partial class OrdersPositionsDashboard
{
    private bool _executionBusy;
    private async Task ModifyPositionAsync(long ticket)
    {
        var position=_book.Positions.FirstOrDefault(p=>p.Ticket==ticket);
        if(position is null || TopLevel.GetTopLevel(this) is not Window owner)return;
        var sl=new TextBox {Text=position.Sl.ToString(System.Globalization.CultureInfo.InvariantCulture)};
        var tp=new TextBox {Text=position.Tp.ToString(System.Globalization.CultureInfo.InvariantCulture)};
        var confirm=new CheckBox {Content=$"Xác nhận sửa #{ticket} · {_book.AccountTradeMode} {_book.AccountLogin}"};
        var status=new TextBlock {Foreground=Brushes.OrangeRed};
        var send=new Button {[LocalizationService.TextProperty] = "Gửi thay đổi"};
        var dialog=new Window {Title="Sửa SL / TP",Width=500,Height=310,WindowStartupLocation=WindowStartupLocation.CenterOwner};
        (double Sl,double Tp)? values=null;
        send.Click+=(_,_)=>
        {
            if(!TryNumber(sl.Text,out double stop) || !TryNumber(tp.Text,out double target) || stop<=0 || target<0 || confirm.IsChecked!=true)
            {status.Text="Nhập SL > 0, TP ≥ 0 và xác nhận tài khoản.";return;}
            values=(stop,target);dialog.Close();
        };
        dialog.Content=new StackPanel {Margin=new Thickness(18),Spacing=10,Children={new TextBlock {[LocalizationService.TextProperty] = "SL (giữ hoặc thu hẹp rủi ro)"},sl,new TextBlock {[LocalizationService.TextProperty] = "TP (0 để bỏ TP theo lựa chọn của bạn)"},tp,confirm,status,send}};
        await dialog.ShowDialog(owner);
        if(values is {} change)await SendActionAsync("MODIFY_POSITION",true,ticket:ticket,sl:change.Sl,tp:change.Tp);
    }
    public void ApplyExecutionStatus(ExecutionSnapshot state)
    {
        Text("ExecutionStatusText").Text = $"{state.Label} · {_book.AccountTradeMode ?? "—"} {_book.AccountLogin} · {state.Reason}";
        Text("ManualModeText").Text = $"{state.Label.ToUpperInvariant()} · {_book.AccountTradeMode ?? "—"}";
        bool ready = state.Fresh && state.Enabled && _book.Available && _book.TerminalConnected && !_executionBusy;
        Button("MarketBuyButton").IsEnabled = ready;
        Button("MarketSellButton").IsEnabled = ready;
        if (state.Recent is { } recent && recent.GetArrayLength() > 0)
        {
            var item = recent[0];
            string id = item.GetProperty("id").GetString() ?? "";
            string outcome = item.GetProperty("state").GetString() ?? "";
            string action = item.GetProperty("command").GetProperty("action").GetString() ?? "";
            string evidence = "";
            if (item.TryGetProperty("result", out var result) && result.ValueKind == JsonValueKind.Object)
            {
                if (result.TryGetProperty("reason", out var reason)) evidence = reason.ToString();
                if (result.TryGetProperty("deal_ticket", out var deal) && deal.TryGetInt64(out long ticket) && ticket > 0) evidence += $" · Deal {ticket}";
            }
            Text("ExecutionRecentText").Text = $"{action} · {outcome} · {id[..Math.Min(8,id.Length)]} · {evidence}";
        }
    }

    private async void ExecutionMode_OnClick(object? sender, RoutedEventArgs e)
    {
        if (_executionBusy || _supervisor is null || sender is not Button { Tag: string mode }) return;
        _executionBusy = true;
        try
        {
            if (mode != "OFF")
            {
                string label = mode == "AUTO" ? "Tự động đặt và quản lý lệnh theo cấu hình" : "Đặt và quản lý lệnh bằng các nút điều khiển";
                if (!await ConfirmExecutionAsync($"{label}\nTài khoản: {_book.AccountLogin} · {_book.AccountTradeMode}\nMáy chủ: {_book.AccountServer}\nSymbol: {_book.Symbol} · Magic: {_book.Magic}\nThiết lập rủi ro hiện tại được áp dụng cho mỗi lệnh.")) return;
            }
            var result = await _supervisor.SetExecutionModeAsync(mode, mode != "OFF");
            bool accepted = result.TryGetProperty("accepted", out var value) && value.ValueKind == JsonValueKind.True;
            SetActionStatus(accepted ? $"Đã chọn chế độ {mode}." : result.GetProperty("code").ToString(), accepted ? Brushes.LightGreen : Brushes.OrangeRed);
        }
        catch (Exception error) { SetActionStatus(error.Message, Brushes.OrangeRed); }
        finally { _executionBusy = false; ApplyExecutionStatus(_supervisor.Execution); }
    }

    private async Task<bool> ConfirmExecutionAsync(string message)
    {
        if (TopLevel.GetTopLevel(this) is not Window owner) return false;
        bool accepted = false;
        var body = new StackPanel { Margin = new Thickness(20), Spacing = 14 };
        body.Children.Add(new TextBlock { Text = message, TextWrapping = TextWrapping.Wrap });
        var check = new CheckBox { [LocalizationService.TextProperty] = "Tôi xác nhận tài khoản và chế độ ở trên" };
        body.Children.Add(check);
        var buttons = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 10 };
        var apply = new Button { [LocalizationService.TextProperty] = "Áp dụng", IsEnabled = false, Classes = { "primary" } };
        var cancel = new Button { [LocalizationService.TextProperty] = "Hủy", Classes = { "secondary" } };
        buttons.Children.Add(apply); buttons.Children.Add(cancel); body.Children.Add(buttons);
        var dialog = new Window { Title = "Chế độ giao dịch", Width = 500, SizeToContent = SizeToContent.Height,
            WindowStartupLocation = WindowStartupLocation.CenterOwner, Content = body, Background = new SolidColorBrush(Color.Parse("#031426")) };
        check.IsCheckedChanged += (_, _) => apply.IsEnabled = check.IsChecked == true;
        apply.Click += (_, _) => { accepted = true; dialog.Close(); }; cancel.Click += (_, _) => dialog.Close();
        await dialog.ShowDialog(owner);
        return accepted;
    }

    private async void PendingEntry_OnClick(object? sender, RoutedEventArgs e)
    {
        if (_supervisor is null || _executionBusy || TopLevel.GetTopLevel(this) is not Window owner) return;
        var types = new ComboBox { ItemsSource = new[] { "BUY_STOP", "SELL_STOP", "BUY_LIMIT", "SELL_LIMIT" }, SelectedIndex = 0 };
        var price = new TextBox { PlaceholderText = "Giá đặt lệnh" };
        var confirm = new CheckBox { Content = $"Xác nhận đặt lệnh trên {_book.AccountTradeMode} {_book.AccountLogin}" };
        var note = new TextBlock { [LocalizationService.TextProperty] = "Khối lượng, SL và TP lấy từ biểu mẫu bên phải; để trống SL/TP để dùng cấu hình.", TextWrapping = TextWrapping.Wrap };
        var submit = new Button { [LocalizationService.TextProperty] = "Gửi lệnh chờ", Classes = { "primary" } };
        var body = new StackPanel { Margin = new Thickness(18), Spacing = 10, Children = { note, types, price, confirm, submit } };
        var dialog = new Window { Title = "Đặt lệnh chờ", Width = 460, SizeToContent = SizeToContent.Height,
            WindowStartupLocation = WindowStartupLocation.CenterOwner, Content = body, Background = new SolidColorBrush(Color.Parse("#031426")) };
        submit.Click += async (_, _) =>
        {
            if (!TryNumber(price.Text, out double pendingPrice) || !TryNumber(Box("ManualLotBox").Text, out double volume) || confirm.IsChecked != true)
            { note.Text = "Nhập giá, khối lượng hợp lệ và xác nhận tài khoản."; return; }
            submit.IsEnabled = false; _executionBusy = true;
            try
            {
                string type = (string)types.SelectedItem!;
                var result = await _supervisor.ExecuteManualActionAsync("PLACE_PENDING", true, volume:volume,
                    slPoints:NullableNumber(Box("ManualSlBox").Text), tpPoints:NullableNumber(Box("ManualTpBox").Text), price:pendingPrice,
                    side:type.Split('_')[0], orderType:type);
                note.Text = $"{result.Code} · {result.Message}";
            }
            catch (Exception error) { note.Text = error.Message; }
            finally { _executionBusy = false; /* Require a new dialog for a new intent. */ }
        };
        await dialog.ShowDialog(owner);
    }

    private async void SymbolInfo_OnClick(object? sender, RoutedEventArgs e)
    {
        if (TopLevel.GetTopLevel(this) is not Window owner) return;
        var info = new TextBlock { Margin = new Thickness(20), TextWrapping = TextWrapping.Wrap,
            Text = $"{_book.Symbol} · {_book.AccountServer}\nLot: {_book.VolumeMin} – {_book.VolumeMax}; bước {_book.VolumeStep}\nPoint: {_book.Point}; bước giá: {_book.TickSize}\nGiá trị tick/lot: {_book.TickValue} {_book.AccountCurrency}\nStops: {_book.StopsLevel} points; Freeze: {_book.FreezeLevel} points\nSpread hiện tại: {_book.SpreadPoints:0.##} points\nĐơn vị SL/TP trong biểu mẫu: số points × {_book.Point}." };
        await new Window { Title = "Thông số symbol từ MT5", Width = 480, SizeToContent = SizeToContent.Height,
            WindowStartupLocation = WindowStartupLocation.CenterOwner, Content = info, Background = new SolidColorBrush(Color.Parse("#031426")) }.ShowDialog(owner);
    }
}
