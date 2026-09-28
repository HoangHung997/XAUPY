using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Primitives;
using Avalonia.Media;

namespace XAUPY.Desktop;

/// <summary>Zoom text and its controls together, retaining access through scrolling.</summary>
public sealed class WorkspaceScale : UserControl
{
    private readonly LayoutTransformControl _transform = new();
    private readonly ScrollViewer _scroll;
    public double Zoom => AppearanceService.FontScale / 100.0;
    public Control? Workspace
    {
        get => _transform.Child;
        set { _transform.Child = value; InvalidateMeasure(); }
    }

    public WorkspaceScale()
    {
        _scroll = new ScrollViewer { Content = _transform,
            HorizontalScrollBarVisibility = ScrollBarVisibility.Auto,
            VerticalScrollBarVisibility = ScrollBarVisibility.Auto };
        Content = _scroll;
        AttachedToVisualTree += (_, _) => AppearanceService.Changed += AppearanceChanged;
        DetachedFromVisualTree += (_, _) => AppearanceService.Changed -= AppearanceChanged;
    }
    private void AppearanceChanged()
    {
        _scroll.Offset = default;
        InvalidateMeasure();
    }
    protected override Size MeasureOverride(Size availableSize)
    {
        if (Workspace is { } workspace)
        {
            // At 100% this is the original responsive canvas. Larger scales
            // retain that canvas instead of forcing large glyphs into fixed rows.
            if (double.IsFinite(availableSize.Width)) workspace.Width = Math.Max(1, availableSize.Width / Math.Min(1, Zoom) - workspace.Margin.Left - workspace.Margin.Right);
            if (double.IsFinite(availableSize.Height)) workspace.Height = Math.Max(1, availableSize.Height / Math.Min(1, Zoom) - workspace.Margin.Top - workspace.Margin.Bottom);
            _transform.LayoutTransform = new ScaleTransform(Zoom, Zoom);
        }
        return base.MeasureOverride(availableSize);
    }
}
