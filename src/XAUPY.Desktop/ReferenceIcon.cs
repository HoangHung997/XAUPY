using Avalonia;
using Avalonia.Controls;
using Avalonia.Media;

namespace XAUPY.Desktop;

/// <summary>Small native vector icons shared by the reference dashboard cards.</summary>
public sealed class ReferenceIcon : Control
{
    public static readonly StyledProperty<string> KindProperty = AvaloniaProperty.Register<ReferenceIcon, string>(nameof(Kind), "document");
    public static readonly StyledProperty<IBrush> TintProperty = AvaloniaProperty.Register<ReferenceIcon, IBrush>(nameof(Tint), Brushes.DeepSkyBlue);
    public string Kind { get => GetValue(KindProperty); set => SetValue(KindProperty, value); }
    public IBrush Tint { get => GetValue(TintProperty); set => SetValue(TintProperty, value); }
    static ReferenceIcon() => AffectsRender<ReferenceIcon>(KindProperty, TintProperty);
    private static readonly Dictionary<string,string> Paths = new()
    {
        ["document"] = "M5,2 L14,2 20,8 20,22 5,22 Z M14,2 L14,8 20,8 M8,12 L17,12 M8,16 L17,16 M8,19 L15,19",
        ["compare"] = "M3,7 L20,7 M16,3 L20,7 16,11 M21,17 L4,17 M8,13 L4,17 8,21",
        ["bars"] = "M3,21 L3,12 7,12 7,21 Z M10,21 L10,4 14,4 14,21 Z M17,21 L17,8 21,8 21,21 Z",
        ["calculator"] = "M5,2 L19,2 19,22 5,22 Z M8,5 L16,5 16,9 8,9 Z M8,13 L9,13 M12,13 L13,13 M16,13 L17,13 M8,17 L9,17 M12,17 L13,17 M16,17 L17,17",
        ["globe"] = "M22,12 A10,10 0 1 1 2,12 A10,10 0 1 1 22,12 M2,12 L22,12 M12,2 C5,8 5,16 12,22 M12,2 C19,8 19,16 12,22 M4,6 C9,9 15,9 20,6 M4,18 C9,15 15,15 20,18",
        ["pulse"] = "M1,13 L6,13 9,4 13,21 16,10 19,13 23,13",
        ["link"] = "M9,15 L15,9 M10,7 L13,4 C19,-2 26,5 20,11 L17,14 M7,10 L4,13 C-2,19 5,26 11,20 L14,17",
        ["user"] = "M16,6 A4,4 0 1 1 8,6 A4,4 0 1 1 16,6 M3,22 L3,18 C3,11 21,11 21,18 L21,22 Z",
        ["transfer"] = "M7,22 L7,2 M2,7 L7,2 12,7 M17,2 L17,22 M12,17 L17,22 22,17",
        ["monitor"] = "M2,3 L22,3 22,17 2,17 Z M12,17 L12,22 M7,22 L17,22",
        ["plug"] = "M8,2 L8,8 M16,2 L16,8 M5,8 L19,8 19,11 C19,16 5,16 5,11 Z M12,16 L12,22",
        ["folder"] = "M2,6 L9,6 12,9 22,9 19,21 2,21 Z M2,6 L2,3 9,3 12,6 21,6 21,9",
        ["palette"] = "M22,10 C22,3 15,1 10,2 C2,3 0,12 4,18 C6,22 12,23 14,20 C15,17 10,17 12,14 C15,11 22,15 22,10 M7,8 L7,8.1 M11,5 L11,5.1 M17,7 L17,7.1 M6,14 L6,14.1",
        ["bell"] = "M5,17 L5,10 C5,1 19,1 19,10 L19,17 22,20 2,20 Z M10,22 L14,22 M12,1 L12,3",
        ["shield"] = "M3,5 L12,1 21,5 20,14 C19,18 15,21 12,23 C9,21 5,18 4,14 Z M12,4 L12,19",
        ["database"] = "M3,5 C3,0 21,0 21,5 C21,10 3,10 3,5 M3,5 L3,19 C3,24 21,24 21,19 L21,5 M3,12 C3,17 21,17 21,12",
        ["power"] = "M12,1 L12,12 M6,5 C-2,12 3,23 12,23 C21,23 26,12 18,5",
        ["cloud"] = "M6,20 C-1,20 0,10 6,10 C6,0 20,0 20,10 C27,12 24,20 19,20 Z M12,19 L12,8 M8,12 L12,8 16,12",
        ["info"] = "M22,12 A10,10 0 1 1 2,12 A10,10 0 1 1 22,12 M12,10 L12,18 M12,6 L12,6.2"
    };
    public override void Render(DrawingContext context)
    {
        base.Render(context);
        var size = Math.Min(Bounds.Width, Bounds.Height);
        if (size <= 0) return;
        using (context.PushTransform(Matrix.CreateScale(size / 26, size / 26) * Matrix.CreateTranslation((Bounds.Width-size)/2 + size/26, (Bounds.Height-size)/2 + size/26)))
            context.DrawGeometry(null, new Pen(Tint, 1.8, lineCap:PenLineCap.Round, lineJoin:PenLineJoin.Round), Geometry.Parse(Paths.GetValueOrDefault(Kind,Paths["document"])));
    }
}
