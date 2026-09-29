using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Threading;
using Avalonia.VisualTree;
using XAUPY.Desktop;
using XAUPY.Ipc;

internal static class ReadinessRepairChecks
{
    public static void Run(Action<bool,string> check, EngineProcessSupervisor supervisor,
        SettingsDashboard settings, Action<Task> complete)
    {
        object? Invoke(string name) => typeof(SettingsDashboard).GetMethod(name,BindingFlags.Instance|BindingFlags.NonPublic)!.Invoke(settings,null);
        bool DraftRejected()
        {
            try { Invoke("RequireCleanRestoreDrafts"); return false; }
            catch(TargetInvocationException error) when(error.InnerException is InvalidOperationException) { return true; }
        }
        check(!settings.HasUnsavedChanges,"RC2 settings starts with a clean restore baseline");
        var permission=settings.FindControl<CheckBox>("AllowRealAccount")!;
        bool prior=permission.IsChecked==true;
        permission.IsChecked=!prior;
        check(settings.HasUnsavedChanges && DraftRejected(),"RC2 unsaved settings cannot be silently discarded by restore");
        permission.IsChecked=prior;
        settings.HasConflictingDraft=()=>true;
        check(DraftRejected(),"RC2 restore also protects drafts in the other four editors");
        settings.HasConflictingDraft=null;
        check(!settings.HasUnsavedChanges,"RC2 reverting the local preference restores a clean baseline");
        check(settings.FindControl<TextBox>("BridgeModeReadOnly") is {IsReadOnly:true},
            "RC2 sole Bridge implementation is read-only, not a decorative mode selector");
        check(new ToolsDashboard().FindControl<TextBox>("ConfigScopeReadOnly") is {IsReadOnly:true},
            "RC2 sole Tools profile scope is not a decorative selector");

        var before=supervisor.GetSettingsAsync();complete(before);
        var backup=supervisor.CreateBackupAsync();complete(backup);
        string id=backup.Result.GetProperty("backup").GetProperty("id").GetString()!;
        var previewTask=supervisor.PreviewBackupRestoreAsync(id);complete(previewTask);
        var preview=previewTask.Result.GetProperty("preview");
        check(preview.GetProperty("execution_after").GetString()=="OFF" &&
            !preview.GetProperty("permission_escalation_allowed").GetBoolean(),
            "RC2 actual IPC restore preview exposes OFF and no permission escalation");
        string token=preview.GetProperty("preview_hash").GetString()!;
        var denied=supervisor.RestoreBackupAsync(id,token,false);complete(denied);
        check(!denied.Result.GetProperty("ok").GetBoolean() && denied.Result.ToString().Contains("RESTORE_CONFIRMATION_REQUIRED"),
            "RC2 actual IPC refuses restore without new confirmation");
        var stale=supervisor.RestoreBackupAsync(id,new string('0',64),true);complete(stale);
        check(!stale.Result.GetProperty("ok").GetBoolean() && stale.Result.ToString().Contains("RESTORE_PREVIEW_CHANGED"),
            "RC2 actual IPC refuses an unreviewed or stale preview hash");
        bool? decision=null;
        var build=typeof(SettingsDashboard).GetMethod("BuildRestoreReview",BindingFlags.Static|BindingFlags.NonPublic)!;
        var dialog=(Window)build.Invoke(null,[preview,(Action<bool>)(value=>decision=value)])!;
        dialog.Show();Dispatcher.UIThread.RunJobs();
        var apply=dialog.GetVisualDescendants().OfType<Button>().Single(c=>c.Name=="RestoreReviewApply");
        var cancel=dialog.GetVisualDescendants().OfType<Button>().Single(c=>c.Name=="RestoreReviewCancel");
        var consent=dialog.GetVisualDescendants().OfType<CheckBox>().Single(c=>c.Name=="RestoreReviewConfirm");
        var text=dialog.GetVisualDescendants().OfType<TextBox>().Single(c=>c.Name=="RestorePreviewText");
        check(!apply.IsEnabled && text.Text!.Contains("max_daily_loss_pct") && text.Text.Contains("OFF"),
            "RC2 restore dialog displays before/after risk and requires visible consent");
        consent.IsChecked=true;check(apply.IsEnabled,"RC2 reviewing restore enables only its own confirmation button");
        consent.IsChecked=false;check(!apply.IsEnabled,"RC2 withdrawing consent disables restore immediately");
        cancel.RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
        check(decision==false,"RC2 cancelling the real restore dialog does not invoke restoration");
        var afterCancel=supervisor.GetSettingsAsync();complete(afterCancel);
        check(before.Result.GetProperty("settings").GetRawText()==afterCancel.Result.GetProperty("settings").GetRawText(),
            "RC2 preview, rejected requests and dialog cancel preserve persisted settings");
        var restored=supervisor.RestoreBackupAsync(id,token,true);complete(restored);
        check(restored.Result.GetProperty("ok").GetBoolean() && !restored.Result.GetProperty("trading_enabled").GetBoolean()
            && supervisor.Execution.Mode=="OFF" && !supervisor.Execution.Enabled,
            "RC2 successful reviewed restore immediately refreshes Desktop execution as OFF");
        complete(settings.EnsureLoadedAsync(true));
        TestChartFiles(check);
        var profileTask=supervisor.GetActiveConfigAsync();complete(profileTask);
        TestPresetAndDrawdown(check,profileTask.Result);
    }

    private static void TestChartFiles(Action<bool,string> check)
    {
        string root=Directory.CreateTempSubdirectory("xaupy-chart-repair-").FullName;
        var method=typeof(MarketChartControl).GetMethod("ReadChartData",BindingFlags.Static|BindingFlags.NonPublic)!;
        (string Symbol,string Timeframe,MarketBar[] Bars) Read(string path)=>((string,string,MarketBar[]))method.Invoke(null,[path])!;
        bool Rejected(string path) {try{Read(path);return false;}catch(TargetInvocationException e) when(e.InnerException is InvalidDataException or FormatException or Microsoft.VisualBasic.FileIO.MalformedLineException){return true;}}
        try
        {
            string file=Path.Combine(root,"M5.csv");
            File.WriteAllText(file,"\uFEFFtime,open,high,low,close,tick_volume,symbol,timeframe,comment\n60,10,12,9,11,3,XAUUSD,M5,\"quoted, comma\"\n120,11,13,10,12,4,XAUUSD,M5,\"escaped \"\"quote\"\"\"\n");
            var data=Read(file);check(data.Symbol=="XAUUSD" && data.Timeframe=="M5" && data.Bars.Length==2,
                "RC2 chart CSV handles quoted fields and UTF-8 without inventing a symbol");
            File.WriteAllText(file,"time,open,high,low,close\n60,10,12,9,11\n120,11,13,10,12\n");
            File.WriteAllText(Path.Combine(root,"manifest.json"),"{\"symbol\":\"XAUUSD\",\"timeframes\":{\"M5\":{\"path\":\"M5.csv\"}}}");
            data=Read(file);check(data.Symbol=="XAUUSD" && data.Timeframe=="M5",
                "RC2 relative chart manifest resolves against its directory, not the app working directory");
            File.Delete(Path.Combine(root,"manifest.json"));
            foreach(string rows in new[]{
                "time,open,high,low,close,symbol,timeframe\n60,10,12,9,11,XAUUSD,M1\n120,10,12,9,11,BTCUSD,M1\n",
                "time,open,high,low,close,symbol,timeframe\n60,10,12,9,11,XAUUSD,M1\n120,10,12,9,11,XAUUSD,M5\n",
                "time,open,high,low,close\n60,10,12,9,11\n60,10,12,9,11\n",
                "time,open,high,low,close,close\n60,10,12,9,11,11\n"})
            {
                File.WriteAllText(file,rows);check(Rejected(file),"RC2 chart rejects mixed identity, duplicate bars or ambiguous CSV columns");
            }
        }
        finally { Directory.Delete(root,true); }
    }

    private static void TestPresetAndDrawdown(Action<bool,string> check,JsonElement profile)
    {
        var optimizer=new OptimizerDashboard();
        object? Invoke(string name,params object[] args)=>typeof(OptimizerDashboard).GetMethod(name,BindingFlags.Instance|BindingFlags.NonPublic)!.Invoke(optimizer,args);
        Invoke("InitializeRangesFromActiveProfile",profile);
        string Snapshot()=>JsonSerializer.Serialize(Invoke("BuildParameterRanges"));
        var ranges=JsonSerializer.SerializeToNode(Invoke("BuildParameterRanges"))!;
        var preset=new JsonObject { ["schema_version"]=1,["parameter_ranges"]=ranges };
        string before=Snapshot();
        Invoke("ApplyPreset",JsonSerializer.SerializeToElement(preset));
        Dispatcher.UIThread.RunJobs();
        check(Snapshot()==before,"RC2 valid optimizer preset round-trips all active ranges");
        Invoke("MarkPresetSaved","fixture-optimizer.json");
        Dispatcher.UIThread.RunJobs();
        check(optimizer.FindControl<TextBox>("OptimizerPresetName") is {IsReadOnly:true,Text:"fixture-optimizer.json"},
            "RC2 preset name is a real loaded-file identity, not a one-option selector");
        bool Rejected(JsonObject value)
        {
            try {Invoke("ApplyPreset",JsonSerializer.SerializeToElement(value));return false;}
            catch(TargetInvocationException e) when(e.InnerException is InvalidDataException){return true;}
        }
        var bad=(JsonObject)preset.DeepClone();bad["parameter_ranges"]![0]!["values"]=new JsonArray("M1","H1");
        check(Rejected(bad)&&Snapshot()==before,"RC2 non-contiguous preset cannot silently add intermediate timeframes");
        bad=(JsonObject)preset.DeepClone();bad["parameter_ranges"]!.AsArray().RemoveAt(0);
        check(Rejected(bad)&&Snapshot()==before,"RC2 missing preset ranges cannot leave a half-old half-new sweep");
        bad=(JsonObject)preset.DeepClone();bad["parameter_ranges"]!.AsArray().Last()!["step"]="invalid";
        check(Rejected(bad)&&Snapshot()==before,"RC2 malformed later preset row is rejected before any control changes");
        var chartView=new BacktestDashboard();
        var chart=chartView.FindControl<BacktestChartControl>("DrawdownChart")!;
        chart.SetDrawdownData(new[]{new BacktestDrawdownPoint(60,50,1),new BacktestDrawdownPoint(120,200,2)});
        var selector=chartView.FindControl<ComboBox>("DrawdownUnitCombo")!;
        selector.SelectedIndex=1;Dispatcher.UIThread.RunJobs();
        var metric=typeof(BacktestChartControl).GetMethod("DrawdownValue",BindingFlags.Instance|BindingFlags.NonPublic)!;
        check(selector.IsEnabled && chart.DrawdownUnit=="MONEY" && (double)metric.Invoke(chart,[new BacktestDrawdownPoint(120,200,2)])! == 200,
            "RC2 drawdown selector renders actual money drawdown instead of a disabled placeholder");
        selector.SelectedIndex=0;Dispatcher.UIThread.RunJobs();
        check(chart.DrawdownUnit=="PERCENT" && (double)metric.Invoke(chart,[new BacktestDrawdownPoint(120,200,2)])! == 2,
            "RC2 drawdown percentage selection restores the actual percent series");
    }

    public static void CheckMetadataTranslation(Action<bool,string> check)
    {
        var chart=new MarketChartControl();
        var menu=chart.ContextMenu!.Items.OfType<MenuItem>().ToArray();
        var window=new Window {[LocalizationService.TitleProperty]="Xác nhận khôi phục an toàn",Content=new TextBox{Text="User profile chưa dịch"}};
        var originalContent=window.Content;
        LocalizationService.Apply("English");
        check(menu.First().Header?.ToString()=="Load complete CSV/JSON history…" &&
            menu.Any(m=>m.Header?.ToString()=="Compare an asset from a CSV/JSON file…"),
            "RC2 existing chart menu metadata changes language, including file-based comparison scope");
        check(window.Title=="Review safe backup restoration" && ReferenceEquals(window.Content,originalContent),
            "RC2 window title translation never replaces content or editable user text");
        window.Title="User-selected report 123";
        LocalizationService.Apply("Tiếng Việt");
        check(menu.First().Header?.ToString()=="Tải toàn bộ lịch sử CSV/JSON…" && window.Title=="User-selected report 123",
            "RC2 metadata restores Vietnamese but preserves runtime-overridden titles");
        window.Close();
    }
}
