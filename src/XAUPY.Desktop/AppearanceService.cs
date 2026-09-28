using System.Globalization;
using System.Runtime.CompilerServices;
using System.Text.Json;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Primitives;
using Avalonia.Media;
using Avalonia.Platform;
using XAUPY.Ipc;

namespace XAUPY.Desktop;

public static class AppearanceService
{
    private static readonly ConditionalWeakTable<Control, object> ScaledControls = new();
    public static readonly AttachedProperty<double> BaseFontSizeProperty =
        AvaloniaProperty.RegisterAttached<Control, double>("BaseFontSize", typeof(AppearanceService), double.NaN);

    static AppearanceService()
    {
        Window.IsVisibleProperty.Changed.AddClassHandler<Window>((window, _) =>
        {
            if (!window.IsVisible || window is MainWindow || window.Content is not Control content || content is WorkspaceScale) return;
            window.Content = null;
            window.Content = new WorkspaceScale { Workspace = content };
        });
        BaseFontSizeProperty.Changed.AddClassHandler<Control>((control, _) =>
        {
            ScaledControls.GetValue(control, _ => new object());
            ApplyControlFont(control);
        });
    }

    // WorkspaceScale applies the requested zoom to both text and its geometry.
    public static double Scale(double size) => size;
    public static event Action? Changed;
    private static void ApplyControlFont(Control control)
    {
        double size = Scale(control.GetValue(BaseFontSizeProperty));
        if (control is TextBlock text) text.SetCurrentValue(TextBlock.FontSizeProperty, size);
        else if (control is TemplatedControl input) input.SetCurrentValue(TemplatedControl.FontSizeProperty, size);
    }

    public static string Theme {get;private set;}="N30 Dark";
    public static int FontScale {get;private set;}=100;
    public static void ApplySaved()
    {
        var preferences=EngineProcessSupervisor.ReadAppearancePreference();
        Apply(preferences.Theme,preferences.FontScale);
    }
    public static void Apply(string theme,int fontScale)
    {
        if(Application.Current is not {} app)return;
        Theme=theme is "N30 Dark" or "N30 Contrast"?theme:"N30 Dark";
        FontScale=fontScale is >=90 and <=150?fontScale:100;
        using var stream=AssetLoader.Open(new Uri("avares://XAUPY.Desktop/Assets/appearance-tokens.json"));
        using var catalog=JsonDocument.Parse(stream);
        foreach(var token in catalog.RootElement.GetProperty("colors").EnumerateArray())
        {
            string hex=token.GetString()!;var color=Color.Parse(hex);
            if(Theme=="N30 Contrast")
            {
                double brightness=.2126*color.R+.7152*color.G+.0722*color.B;
                color=brightness<75?Color.FromArgb(color.A,(byte)(color.R*.35),(byte)(color.G*.35),(byte)(color.B*.35)):
                    Color.FromArgb(color.A,(byte)Math.Min(255,color.R*1.15+10),(byte)Math.Min(255,color.G*1.15+10),(byte)Math.Min(255,color.B*1.15+10));
            }
            app.Resources["Color_"+hex[1..]]=color;
            app.Resources["Brush_"+hex[1..]]=new SolidColorBrush(color);
        }
        foreach(var token in catalog.RootElement.GetProperty("fonts").EnumerateArray())
        {
            double size=token.GetDouble();string key=size.ToString("0.####",CultureInfo.InvariantCulture).Replace('.','_');
            app.Resources["Font_"+key]=size;
        }
        foreach (var entry in ScaledControls) ApplyControlFont(entry.Key);
        Changed?.Invoke();
    }
}
