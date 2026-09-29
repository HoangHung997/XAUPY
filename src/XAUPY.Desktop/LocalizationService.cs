using System.Text.Json;
using System.Runtime.CompilerServices;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Platform;
using XAUPY.Ipc;

namespace XAUPY.Desktop;

public static class LocalizationService
{
    private static Dictionary<string,string> _english=new(StringComparer.Ordinal);
    private static readonly ConditionalWeakTable<Control, object> Labels = new();
    private static bool _updating;
    public static readonly AttachedProperty<string?> TextProperty =
        AvaloniaProperty.RegisterAttached<Control, string?>("Text", typeof(LocalizationService));
    // Separate metadata tags: Window is a ContentControl, so using Text for a
    // title would replace its content. Only explicitly tagged labels translate.
    public static readonly AttachedProperty<string?> HeaderProperty =
        AvaloniaProperty.RegisterAttached<Control, string?>("Header", typeof(LocalizationService));
    public static readonly AttachedProperty<string?> TitleProperty =
        AvaloniaProperty.RegisterAttached<Control, string?>("Title", typeof(LocalizationService));
    public static string? GetHeader(Control control) => control.GetValue(HeaderProperty);
    public static void SetHeader(Control control, string? value) => control.SetValue(HeaderProperty, value);
    public static string? GetTitle(Control control) => control.GetValue(TitleProperty);
    public static void SetTitle(Control control, string? value) => control.SetValue(TitleProperty, value);
    public static string? GetText(Control control) => control.GetValue(TextProperty);
    public static void SetText(Control control, string? value) => control.SetValue(TextProperty, value);
    static LocalizationService()
    {
        TextBlock.TextProperty.Changed.AddClassHandler<TextBlock>((control, _) => ForgetOverriddenLabel(control));
        ContentControl.ContentProperty.Changed.AddClassHandler<ContentControl>((control, _) => ForgetOverriddenLabel(control));
        MenuItem.HeaderProperty.Changed.AddClassHandler<MenuItem>((control, _) =>
        {
            if (!_updating && control.GetValue(HeaderProperty) is not null) control.ClearValue(HeaderProperty);
        });
        Window.TitleProperty.Changed.AddClassHandler<Window>((control, _) =>
        {
            if (!_updating && control.GetValue(TitleProperty) is not null) control.ClearValue(TitleProperty);
        });
        foreach (var property in new[] { TextProperty, HeaderProperty, TitleProperty })
            property.Changed.AddClassHandler<Control>((control, _) =>
            {
                Labels.GetValue(control, _ => new object());
                UpdateLabel(control);
            });
    }
    private static void ForgetOverriddenLabel(Control control)
    {
        if (!_updating && control.GetValue(TextProperty) is not null) control.ClearValue(TextProperty);
    }
    private static void UpdateLabel(Control control)
    {
        bool wasUpdating = _updating;
        try
        {
            _updating = true;
            if (control.GetValue(TextProperty) is { } source)
            {
                if (control is TextBlock text) text.SetCurrentValue(TextBlock.TextProperty, T(source));
                else if (control is ContentControl content) content.SetCurrentValue(ContentControl.ContentProperty, T(source));
            }
            if (control is MenuItem menu && control.GetValue(HeaderProperty) is { } header)
                menu.SetCurrentValue(MenuItem.HeaderProperty, T(header));
            if (control is Window window && control.GetValue(TitleProperty) is { } title)
                window.SetCurrentValue(Window.TitleProperty, T(title));
        }
        finally { _updating = wasUpdating; }
    }
    public static string Language {get;private set;}="Tiếng Việt";
    public static void ApplySaved() => Apply(EngineProcessSupervisor.ReadAppearancePreference().Language);
    public static void Apply(string language)
    {
        if(Application.Current is not {} app)return;
        Language=language=="English"?"English":"Tiếng Việt";
        using var stream=AssetLoader.Open(new Uri("avares://XAUPY.Desktop/Assets/localization.json"));
        using var catalog=JsonDocument.Parse(stream);
        foreach(var row in catalog.RootElement.EnumerateObject())
        {
            string vi=row.Value.GetProperty("vi").GetString()!,en=row.Value.GetProperty("en").GetString()!;
            if(vi.StartsWith("{}"))vi=vi[2..];if(en.StartsWith("{}"))en=en[2..];
            _english[vi]=en;
            app.Resources["Text_"+row.Name]=Language=="English"?en:vi;
        }
        // Only explicitly tagged UI labels participate. User/profile names,
        // editable JSON and broker-provided text are never translated implicitly.
        foreach (var label in Labels) UpdateLabel(label.Key);
    }
    public static string T(string value)
    {
        return Language=="English" && _english.TryGetValue(value,out var translated)?translated:value;
    }
}
