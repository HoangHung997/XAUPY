using Avalonia;
using Avalonia.Markup.Xaml;

namespace XAUPY.Desktop;

/// <summary>A localized initial value that cannot later overwrite runtime data.</summary>
public sealed class InitialTextExtension(string key) : MarkupExtension
{
    public override object ProvideValue(IServiceProvider serviceProvider) =>
        Application.Current?.TryGetResource("Text_" + key, null, out var value) == true ? value ?? "" : "";
}
