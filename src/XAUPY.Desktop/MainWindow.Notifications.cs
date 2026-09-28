using Avalonia.Controls.Notifications;
using XAUPY.Ipc;

namespace XAUPY.Desktop;

public partial class MainWindow
{
    private WindowNotificationManager? _notifications;
    private long _lastNotificationSequence;
    private bool _notificationCursorInitialized;
    private void Notify(string title,string message,bool error=false)
    {
        _notifications ??= new WindowNotificationManager(this) {Position=NotificationPosition.TopRight,MaxItems=3};
        _notifications.Show(new Notification(title,message,error?NotificationType.Error:NotificationType.Information,TimeSpan.FromSeconds(error?10:5)));
    }
    private void NotifyEngineChange(EngineStateChangedEventArgs state)
    {
        if(_lastEngineState==state.State || _lastEngineState is null)return;
        bool error=state.State is EngineConnectionState.Faulted or EngineConnectionState.MissingEngine;
        if(error ? _engineSupervisor.ShowSystemErrors : _engineSupervisor.ShowConnectionChanges)
            Notify(error?"Lỗi hệ thống":"Kết nối Engine",state.Detail,error);
    }
    private void NotifySystemAlerts(EngineStateChangedEventArgs state)
    {
        if(state.Monitoring is not {} monitoring || !monitoring.TryGetProperty("alerts",out var alerts))return;
        if(!_notificationCursorInitialized)
        {
            _lastNotificationSequence=alerts.EnumerateArray().Select(a=>a.GetProperty("sequence").GetInt64()).DefaultIfEmpty(0).Max();
            _notificationCursorInitialized=true;
            return;
        }
        foreach(var alert in alerts.EnumerateArray().Reverse())
        {
            long sequence=alert.GetProperty("sequence").GetInt64();
            if(sequence<=_lastNotificationSequence)continue;
            // First attachment records the cursor; old errors are still in Journal.
            if(_engineSupervisor.ShowSystemErrors && alert.GetProperty("level").GetString()=="ERROR")
                Notify("Lỗi hệ thống",alert.GetProperty("message").GetString() ?? "",true);
            _lastNotificationSequence=sequence;
        }
    }
}
