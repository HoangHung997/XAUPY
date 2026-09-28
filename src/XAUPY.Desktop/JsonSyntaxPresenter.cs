using Avalonia.Controls.Presenters;
using Avalonia.Media;
using Avalonia.Media.TextFormatting;
using Avalonia.Utilities;

namespace XAUPY.Desktop;

/// <summary>Colors the native editor's own text layout, preserving its caret, selection and input method.</summary>
public sealed class JsonSyntaxPresenter : TextPresenter
{
    private string? _cachedText;
    private IReadOnlyList<JsonColorSpan> _tokens = Array.Empty<JsonColorSpan>();

    protected override TextLayout CreateTextLayout()
    {
        // The native presenter owns composition underlines and the temporary IME text.
        if (!string.IsNullOrEmpty(PreeditText)) return base.CreateTextLayout();
        var text = Text ?? "";
        if (!string.Equals(_cachedText, text, StringComparison.Ordinal))
        {
            _cachedText = text;
            _tokens = Tokenize(text);
        }
        var typeface = new Typeface(FontFamily, FontStyle, FontWeight, FontStretch);
        var styles = _tokens.Select(token => new ValueSpan<TextRunProperties>(token.Start, token.Length,
            new GenericTextRunProperties(typeface, FontSize, foregroundBrush: token.Brush))).ToArray();
        return new TextLayout(text, typeface, FontSize, Foreground,
            textWrapping: TextWrapping.NoWrap, lineHeight: LineHeight,
            letterSpacing: LetterSpacing, textStyleOverrides: styles);
    }

    public static IReadOnlyList<JsonColorSpan> Tokenize(string text)
    {
        var spans = new List<JsonColorSpan>();
        for (int i = 0; i < text.Length;)
        {
            var start = i;
            IBrush? brush = null;
            if (text[i] == '"')
            {
                i++;
                while (i < text.Length)
                {
                    if (text[i] == '\\') { i = Math.Min(i + 2, text.Length); continue; }
                    if (text[i++] == '"') break;
                }
                var next = i;
                while (next < text.Length && char.IsWhiteSpace(text[next])) next++;
                brush = next < text.Length && text[next] == ':' ? KeyBrush : StringBrush;
            }
            else if (text[i] == '-' || char.IsAsciiDigit(text[i]))
            {
                i++;
                while (i < text.Length && (char.IsAsciiDigit(text[i]) || text[i] is '.' or 'e' or 'E' or '+' or '-')) i++;
                brush = NumberBrush;
            }
            else if (char.IsAsciiLetter(text[i]))
            {
                i++;
                while (i < text.Length && char.IsAsciiLetter(text[i])) i++;
                var literal = text[start..i];
                if (literal is "true" or "false") brush = BooleanBrush;
                else if (literal == "null") brush = NullBrush;
            }
            else i++;
            if (brush is not null) spans.Add(new(start, i - start, brush));
        }
        return spans;
    }

    private static readonly IBrush KeyBrush = Brush.Parse("#71E9FF");
    private static readonly IBrush StringBrush = Brush.Parse("#A8E6A3");
    private static readonly IBrush NumberBrush = Brush.Parse("#FFD363");
    private static readonly IBrush BooleanBrush = Brush.Parse("#FF927C");
    private static readonly IBrush NullBrush = Brush.Parse("#C8A4FF");
}

public sealed record JsonColorSpan(int Start, int Length, IBrush Brush);
