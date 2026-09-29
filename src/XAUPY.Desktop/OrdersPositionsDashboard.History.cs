using System.Text.Json;
using Avalonia.Interactivity;
using Avalonia.Media;
using XAUPY.Ipc;

namespace XAUPY.Desktop;

public partial class OrdersPositionsDashboard
{
    private IReadOnlyList<DealSnapshot>? _brokerHistoryRows;
    private string? _brokerHistoryReportId;
    private int _brokerHistoryPage;
    private int _brokerHistoryGeneration;
    private bool _brokerHistoryPageBusy;
    private bool _brokerHistoryMore, _brokerHistoryBusy;
    private void ClearBrokerHistory()
    {
        _brokerHistoryGeneration++; _brokerHistoryPageBusy=false;
        _brokerHistoryRows=null; _brokerHistoryReportId=null; _brokerHistoryPage=0; _brokerHistoryMore=false;
        BrokerHistoryStatus.Text="Ảnh chụp gần nhất • tải lịch sử để tra cứu đầy đủ";
    }
    private static JsonElement BrokerHistoryResult(JsonElement value)
    {
        if (!value.GetProperty("ok").GetBoolean()) throw new InvalidDataException(value.GetProperty("errors").ToString());
        return value.GetProperty("history");
    }
    private async void ImportBrokerHistory_OnClick(object? sender, RoutedEventArgs e)
    {
        if (_supervisor is null || _brokerHistoryBusy) return;
        _brokerHistoryBusy=true;
        var identity=(_book.AccountLogin,_book.AccountServer,_book.Magic);
        try
        {
            var state=BrokerHistoryResult(await _supervisor.StartBrokerHistoryAsync());
            BrokerHistoryStatus.Text="Đang đọc toàn bộ lịch sử từ broker…";
            for (int i=0;i<180 && state.GetProperty("status").GetString()=="RUNNING";i++)
            {
                await Task.Delay(1000);
                state=BrokerHistoryResult(await _supervisor.GetBrokerHistoryStatusAsync());
            }
            if (identity!=(_book.AccountLogin,_book.AccountServer,_book.Magic)) throw new InvalidDataException("Tài khoản đã đổi; tải lại lịch sử của tài khoản hiện tại.");
            if (state.GetProperty("status").GetString()!="COMPLETE") throw new InvalidDataException(state.ToString());
            _brokerHistoryReportId=null;
            await LoadBrokerHistoryAsync(0);
        }
        catch(Exception ex) { BrokerHistoryStatus.Text=ex.Message; }
        finally { _brokerHistoryBusy=false; }
    }
    private async Task LoadBrokerHistoryAsync(int page)
    {
        if (_supervisor is null) return;
        int generation=++_brokerHistoryGeneration;
        string identity=Identity(_book);
        string? symbol=Check("CurrentSymbolHistoryCheck").IsChecked==true ? _book.Symbol : null;
        _brokerHistoryPageBusy=true;
        try
        {
            var value=BrokerHistoryResult(await _supervisor.QueryBrokerHistoryAsync(page,100,
                symbol,_brokerHistoryReportId));
            if(generation!=_brokerHistoryGeneration || identity!=Identity(_book) || symbol!=(Check("CurrentSymbolHistoryCheck").IsChecked==true ? _book.Symbol : null)) return;
            _brokerHistoryRows=value.GetProperty("rows").EnumerateArray().Select(item => OrdersPositionsSnapshot.TryReadDeal(item,out var deal) ? deal : throw new InvalidDataException("Dòng lịch sử broker không hợp lệ")).ToArray();
            _brokerHistoryReportId=value.GetProperty("report_id").GetString();
            _brokerHistoryPage=page; _brokerHistoryMore=value.GetProperty("has_more").GetBoolean();
            BrokerHistoryStatus.Text=$"Trang {page+1} • {value.GetProperty("total")} lần đóng • phí vào/ra đã phân bổ • tải {value.GetProperty("metadata").GetProperty("imported_utc").GetString()}";
            RenderAll();
        }
        catch(Exception ex) { if(generation==_brokerHistoryGeneration)BrokerHistoryStatus.Text=ex.Message; }
        finally { if(generation==_brokerHistoryGeneration)_brokerHistoryPageBusy=false; }
    }
    private async void PreviousBrokerHistory_OnClick(object? sender,RoutedEventArgs e)
    { if(!_brokerHistoryBusy && !_brokerHistoryPageBusy && _brokerHistoryPage>0) await LoadBrokerHistoryAsync(_brokerHistoryPage-1); }
    private async void NextBrokerHistory_OnClick(object? sender,RoutedEventArgs e)
    { if(!_brokerHistoryBusy && !_brokerHistoryPageBusy && _brokerHistoryMore) await LoadBrokerHistoryAsync(_brokerHistoryPage+1); }
    private async Task<JsonElement[]> AllBrokerHistoryAsync()
    {
        if(_supervisor is null || _brokerHistoryReportId is null) throw new InvalidOperationException("Tải toàn bộ từ MT5 trước khi xuất báo cáo lịch sử.");
        var result=new List<JsonElement>();
        string identity=Identity(_book);
        bool onlyCurrent=Check("CurrentSymbolHistoryCheck").IsChecked==true;
        string report=_brokerHistoryReportId;
        string? symbol=Check("CurrentSymbolHistoryCheck").IsChecked==true ? _book.Symbol : null;
        for(int page=0;;page++)
        {
            var data=BrokerHistoryResult(await _supervisor.QueryBrokerHistoryAsync(page,500,symbol,report));
            if(identity!=Identity(_book) || onlyCurrent!=(Check("CurrentSymbolHistoryCheck").IsChecked==true) || _brokerHistoryReportId!=report)
                throw new InvalidDataException("Tài khoản hoặc bộ lọc lịch sử đã đổi khi xuất; file cũ được giữ nguyên.");
            result.AddRange(data.GetProperty("rows").EnumerateArray().Select(r=>r.Clone()));
            if(!data.GetProperty("has_more").GetBoolean()) break;
        }
        return result.ToArray();
    }
}
