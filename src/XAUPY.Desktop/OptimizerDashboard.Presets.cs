using System.Globalization;
using System.Text.Json;

namespace XAUPY.Desktop;

public partial class OptimizerDashboard
{
    private string? _savedPresetSignature;
    private string? PresetSignature()
    {
        try { return JsonSerializer.Serialize(new { ranges=BuildParameterRanges(),
            context=new[]{"OptimizeFromDateBox","OptimizeToDateBox","OptimizeBalanceBox","OptimizeSpreadBox","OptimizeCommissionBox","MinTradesBox","WorkersBox","WalkForwardFoldsBox"}.Select(name=>Box(name).Text).ToArray(),
            train_ratio=CurrentTrainRatio(),rolling=CurrentRolling() }); }
        catch(InvalidDataException) { return null; }
    }
    private void MarkPresetSaved(string name)
    {
        _savedPresetSignature=PresetSignature();Box("OptimizerPresetName").Text=name;
    }
    private void MarkPresetEdited()
    {
        if(_savedPresetSignature is null || _savedPresetSignature!=PresetSignature())
            Box("OptimizerPresetName").Text="Custom";
    }

    // This min/max editor can represent complete presets from the current
    // profile, not arbitrary sparse/non-contiguous parameter sweeps. Reject
    // unsupported data atomically instead of quietly importing only half of it.
    private void ValidatePresetBeforeMutation(JsonElement root)
    {
        if(root.ValueKind!=JsonValueKind.Object || !root.TryGetProperty("schema_version",out var version) ||
           version.ValueKind!=JsonValueKind.Number || !version.TryGetInt32(out int schema) || schema!=1)
            throw new InvalidDataException("Optimizer preset: schema_version phải bằng 1.");
        if(!root.TryGetProperty("parameter_ranges",out var ranges) || ranges.ValueKind!=JsonValueKind.Array)
            throw new InvalidDataException("Preset thiếu parameter_ranges.");
        var expected=new HashSet<string>(new[]{"timeframes.direction","timeframes.pullback","timeframes.trigger"});
        if(_includeRsiRows){expected.Add("pullback.rsi_buy_level");expected.Add("pullback.rsi_sell_level");}
        if(_includeMaPeriod)expected.Add("direction.ma_period");
        foreach(string? path in new[]{_triggerDeltaPath,_slPath,_tpPath})if(path is not null)expected.Add(path);
        expected.UnionWith(_extraRanges.Keys);
        var seen=new HashSet<string>();
        foreach(var item in ranges.EnumerateArray())
        {
            if(item.ValueKind!=JsonValueKind.Object || !item.TryGetProperty("path",out var pathValue) || pathValue.ValueKind!=JsonValueKind.String)
                throw new InvalidDataException("Preset có phạm vi không hợp lệ.");
            string path=pathValue.GetString()!;
            if(!expected.Contains(path) || !seen.Add(path))throw new InvalidDataException("Preset có tham số không hỗ trợ, không hoạt động hoặc trùng: "+path);
            if(path.StartsWith("timeframes.",StringComparison.Ordinal))
            {
                if(!item.TryGetProperty("values",out var values) || values.ValueKind!=JsonValueKind.Array || values.GetArrayLength()==0)
                    throw new InvalidDataException("Preset timeframe phải có values: "+path);
                var indices=values.EnumerateArray().Select(v=>v.ValueKind==JsonValueKind.String?Array.IndexOf(Timeframes,v.GetString()):-1).ToArray();
                if(indices.Any(i=>i<0) || indices.Where((v,i)=>i>0 && v!=indices[i-1]+1).Any())
                    throw new InvalidDataException("Preset timeframe phải tăng liên tiếp; không tự thêm hoặc bỏ khung: "+path);
            }
            else
            {
                if(!TryPresetRange(item,out double min,out double max,out double step) ||
                   !double.IsFinite(min)||!double.IsFinite(max)||!double.IsFinite(step)||max<min||step<=0)
                    throw new InvalidDataException("Preset min/max/step không hợp lệ: "+path);
                if((path.EndsWith("_period",StringComparison.Ordinal)||path.EndsWith("_lookback",StringComparison.Ordinal)) &&
                   (min%1!=0 || max%1!=0 || step%1!=0))throw new InvalidDataException("Chu kỳ/lookback và bước phải là số nguyên: "+path);
            }
        }
        if(!seen.SetEquals(expected))throw new InvalidDataException("Preset không đủ phạm vi của profile hiện tại. Không nạp một phần; chọn đúng profile trước.");
        foreach(string key in new[]{"from_date","to_date","initial_balance","spread_pips","commission_per_lot","min_trades","workers","folds"})
        {
            if(!root.TryGetProperty(key,out var value))continue;
            if(value.ValueKind is not (JsonValueKind.String or JsonValueKind.Number))throw new InvalidDataException("Preset sai kiểu: "+key);
            string text=value.ValueKind==JsonValueKind.String?value.GetString()!:value.ToString();
            if(string.IsNullOrWhiteSpace(text))continue; // empty date/data input remains visibly unfinished
            if(key.EndsWith("_date",StringComparison.Ordinal))
            {
                if(!DateOnly.TryParseExact(text,"yyyy-MM-dd",CultureInfo.InvariantCulture,DateTimeStyles.None,out _))throw new InvalidDataException("Preset ngày sai: "+key);
            }
            else if(!double.TryParse(text,NumberStyles.Float,CultureInfo.InvariantCulture,out double number)||!double.IsFinite(number)||number<0||
                    ((key is "initial_balance" or "min_trades" or "workers" or "folds") && number<=0)||
                    ((key is "min_trades" or "workers" or "folds") && number%1!=0))throw new InvalidDataException("Preset giá trị sai: "+key);
        }
        if(root.TryGetProperty("train_ratio",out var ratio) && (ratio.ValueKind!=JsonValueKind.Number || !ratio.TryGetDouble(out double ratioNumber) || ratioNumber is not (.6 or .7 or .8)))
            throw new InvalidDataException("Preset train_ratio không được biểu mẫu hỗ trợ.");
        if(root.TryGetProperty("rolling",out var rolling) && rolling.ValueKind is not (JsonValueKind.True or JsonValueKind.False))
            throw new InvalidDataException("Preset rolling phải là boolean.");
    }
}
