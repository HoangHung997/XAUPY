using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Platform.Storage;
using System.Diagnostics;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using XAUPY.Ipc;

namespace XAUPY.Desktop;

public partial class ConfigurationEditor : UserControl
{
    private sealed record FieldDescriptor(
        string Path,
        string Kind,
        string SetKey,
        string Description,
        IReadOnlyList<string> EnumValues,
        double? Minimum,
        double? Maximum,
        JsonNode? LockedValue);

    private sealed class FieldBinding
    {
        public required FieldDescriptor Descriptor { get; init; }
        public required Border Row { get; init; }
        public required Control Editor { get; init; }
        public required string GroupKey { get; init; }
    }

    private sealed class GroupBinding
    {
        public required Border Card { get; init; }
        public required List<FieldBinding> Fields { get; init; }
    }

    private static readonly IReadOnlyDictionary<string, (int Order, string Title)> GroupTitles =
        new Dictionary<string, (int, string)>(StringComparer.Ordinal)
        {
            ["profile"] = (1, "01. Profile"),
            ["strategy"] = (2, "02. Strategy"),
            ["timeframes"] = (3, "03. Timeframe & Logic"),
            ["direction"] = (4, "04. Direction"),
            ["pullback"] = (5, "05. Pullback"),
            ["trigger"] = (6, "06. Trigger"),
            ["filters.adx"] = (7, "07. ADX"),
            ["filters.atr"] = (8, "08. ATR"),
            ["filters.open"] = (9, "09. Open Filter"),
            ["entry"] = (10, "10. Entry"),
            ["risk"] = (11, "11. Risk"),
            ["stop_loss"] = (12, "12. Stop Loss"),
            ["take_profit"] = (13, "13. Take Profit"),
            ["take_profit.dynamic"] = (14, "14. Dynamic TP"),
            ["management"] = (15, "15. Trade Management"),
            ["sessions"] = (16, "16. Sessions & Days"),
            ["news"] = (17, "17. News"),
            ["costs"] = (18, "18. Cost Filters"),
            ["execution"] = (19, "19. Execution Identity"),
            ["safety"] = (20, "20. Hard Safety"),
            ["logging"] = (21, "21. Logging"),
        };

    private static readonly FilePickerFileType JsonFileType = new("XAUPY profile JSON")
    {
        Patterns = new[] { "*.json" }
    };

    private static readonly FilePickerFileType SetFileType = new("MetaTrader 5 preset")
    {
        Patterns = new[] { "*.set" }
    };

    private readonly List<FieldBinding> _fields = new();
    private readonly Dictionary<string, GroupBinding> _groups = new(StringComparer.Ordinal);

    private EngineProcessSupervisor? _supervisor;
    private JsonObject? _draft;
    private bool _schemaLoaded;
    private bool _loading;
    private bool _suppressChanges;
    private bool _dirty;
    private EngineConnectionState _lastEngineState = EngineConnectionState.Stopped;
    private string? _lastSetTemplatePath;

    public ConfigurationEditor()
    {
        InitializeComponent();
    }

    public void AttachSupervisor(EngineProcessSupervisor supervisor)
    {
        _supervisor = supervisor;
    }

    public async Task NotifyEngineStateAsync(EngineConnectionState state)
    {
        bool becameReady = state == EngineConnectionState.Ready &&
                           _lastEngineState != EngineConnectionState.Ready;
        _lastEngineState = state;

        if (becameReady)
        {
            _schemaLoaded = false;
            await EnsureLoadedAsync(force: true);
            return;
        }

        if (state != EngineConnectionState.Ready && !_loading)
        {
            SetStatus("Python Engine chưa READY. Editor giữ draft hiện tại và sẽ đồng bộ lại khi Engine kết nối.", Brushes.Gold);
        }
    }

    public async Task EnsureLoadedAsync(bool force = false)
    {
        if (_loading || _supervisor is null)
            return;

        if (_schemaLoaded && !force)
            return;

        if (_supervisor.State != EngineConnectionState.Ready)
        {
            SetStatus("Đang chờ Python Engine READY...", Brushes.Gold);
            return;
        }

        _loading = true;

        try
        {
            SetStatus("Đang tải schema 133 tham số và active profile...", Brushes.LightBlue);

            var schema = await _supervisor.GetConfigSchemaAsync();
            var active = await _supervisor.GetActiveConfigAsync();

            BuildSchema(schema);
            LoadDraft(active, dirty: false);

            _schemaLoaded = true;
            SetStatus("Đã tải active profile. Tất cả tham số canonical đang sẵn sàng chỉnh sửa.", Brushes.LightGreen);
        }
        catch (Exception ex)
        {
            SetStatus($"Không tải được cấu hình: {ex.Message}", Brushes.IndianRed);
        }
        finally
        {
            _loading = false;
        }
    }

    private void BuildSchema(JsonElement schema)
    {
        if (!schema.TryGetProperty("fields", out var fieldsElement) ||
            fieldsElement.ValueKind != JsonValueKind.Array)
        {
            throw new InvalidDataException("Config schema is missing fields.");
        }

        var descriptors = new List<FieldDescriptor>();

        foreach (var field in fieldsElement.EnumerateArray())
        {
            string path = ReadRequiredString(field, "path");
            string kind = ReadRequiredString(field, "kind");
            string setKey = ReadRequiredString(field, "set_key");
            string description = ReadOptionalString(field, "description") ?? string.Empty;

            var enumValues = new List<string>();
            if (field.TryGetProperty("enum", out var enumElement) &&
                enumElement.ValueKind == JsonValueKind.Array)
            {
                foreach (var item in enumElement.EnumerateArray())
                {
                    if (item.ValueKind == JsonValueKind.String && item.GetString() is { } value)
                        enumValues.Add(value);
                }
            }

            double? minimum = TryReadNullableDouble(field, "minimum");
            double? maximum = TryReadNullableDouble(field, "maximum");

            JsonNode? lockedValue = null;
            if (field.TryGetProperty("locked_value", out var lockedElement) &&
                lockedElement.ValueKind != JsonValueKind.Null &&
                lockedElement.ValueKind != JsonValueKind.Undefined)
            {
                lockedValue = JsonNode.Parse(lockedElement.GetRawText());
            }

            descriptors.Add(new FieldDescriptor(
                path,
                kind,
                setKey,
                description,
                enumValues,
                minimum,
                maximum,
                lockedValue));
        }

        _fields.Clear();
        _groups.Clear();

        var host = this.FindControl<StackPanel>("FieldsHost")
            ?? throw new InvalidOperationException("FieldsHost missing.");
        host.Children.Clear();

        foreach (var grouping in descriptors
                     .GroupBy(d => GroupKey(d.Path))
                     .OrderBy(group => GroupTitle(group.Key).Order)
                     .ThenBy(group => group.Key, StringComparer.Ordinal))
        {
            var groupFields = new List<FieldBinding>();
            var content = new StackPanel { Spacing = 7 };

            var title = GroupTitle(grouping.Key);
            content.Children.Add(new TextBlock
            {
                Text = title.Title,
                FontSize = 17,
                FontWeight = FontWeight.SemiBold,
                Foreground = Brushes.White
            });

            content.Children.Add(new TextBlock
            {
                Text = $"{grouping.Count()} tham số",
                FontSize = 11,
                Foreground = new SolidColorBrush(Color.Parse("#8097AE")),
                Margin = new Avalonia.Thickness(0, 0, 0, 5)
            });

            foreach (var descriptor in grouping)
            {
                var binding = CreateFieldRow(descriptor, grouping.Key);
                groupFields.Add(binding);
                _fields.Add(binding);
                content.Children.Add(binding.Row);
            }

            var card = new Border
            {
                Background = new SolidColorBrush(Color.Parse("#0C1929")),
                BorderBrush = new SolidColorBrush(Color.Parse("#193956")),
                BorderThickness = new Avalonia.Thickness(1),
                CornerRadius = new Avalonia.CornerRadius(10),
                Padding = new Avalonia.Thickness(15),
                Child = content
            };

            host.Children.Add(card);
            _groups[grouping.Key] = new GroupBinding
            {
                Card = card,
                Fields = groupFields
            };
        }

        var declaredCount = schema.TryGetProperty("field_count", out var countElement) &&
                            countElement.TryGetInt32(out var count)
            ? count
            : _fields.Count;

        if (declaredCount != _fields.Count)
            throw new InvalidDataException($"Schema field_count={declaredCount} but UI built {_fields.Count} rows.");

        this.FindControl<TextBlock>("FieldCountText")!.Text = $"{_fields.Count} tham số";
        ApplySearchFilter();
    }

    private FieldBinding CreateFieldRow(FieldDescriptor descriptor, string groupKey)
    {
        var rowContent = new StackPanel
        {
            Orientation = Orientation.Horizontal,
            Spacing = 12
        };

        var labelStack = new StackPanel
        {
            Width = 420,
            Spacing = 2,
            VerticalAlignment = VerticalAlignment.Center
        };

        labelStack.Children.Add(new TextBlock
        {
            Text = descriptor.Path,
            FontWeight = FontWeight.SemiBold,
            Foreground = new SolidColorBrush(Color.Parse("#DCE8F4")),
            TextWrapping = TextWrapping.Wrap
        });

        if (!string.IsNullOrWhiteSpace(descriptor.Description))
        {
            labelStack.Children.Add(new TextBlock
            {
                Text = descriptor.Description,
                FontSize = 11,
                Foreground = new SolidColorBrush(Color.Parse("#8097AE")),
                TextWrapping = TextWrapping.Wrap
            });
        }

        rowContent.Children.Add(labelStack);

        Control editor = CreateEditor(descriptor);
        editor.Width = 300;
        editor.VerticalAlignment = VerticalAlignment.Center;
        rowContent.Children.Add(editor);

        var metaStack = new StackPanel
        {
            Width = 270,
            Spacing = 2,
            VerticalAlignment = VerticalAlignment.Center
        };

        metaStack.Children.Add(new TextBlock
        {
            Text = descriptor.SetKey,
            FontSize = 11,
            Foreground = new SolidColorBrush(Color.Parse("#6FA8D8")),
            TextWrapping = TextWrapping.Wrap
        });

        string bounds = BoundsText(descriptor);
        if (!string.IsNullOrWhiteSpace(bounds))
        {
            metaStack.Children.Add(new TextBlock
            {
                Text = bounds,
                FontSize = 11,
                Foreground = new SolidColorBrush(Color.Parse("#8097AE"))
            });
        }

        if (descriptor.LockedValue is not null)
        {
            metaStack.Children.Add(new TextBlock
            {
                Text = $"LOCKED = {descriptor.LockedValue}",
                FontSize = 11,
                FontWeight = FontWeight.Bold,
                Foreground = Brushes.Gold
            });
            editor.IsEnabled = false;
        }

        rowContent.Children.Add(metaStack);

        var row = new Border
        {
            Background = new SolidColorBrush(Color.Parse("#091625")),
            BorderBrush = new SolidColorBrush(Color.Parse("#15314B")),
            BorderThickness = new Avalonia.Thickness(1),
            CornerRadius = new Avalonia.CornerRadius(7),
            Padding = new Avalonia.Thickness(12, 9),
            Child = rowContent
        };

        return new FieldBinding
        {
            Descriptor = descriptor,
            Row = row,
            Editor = editor,
            GroupKey = groupKey
        };
    }

    private Control CreateEditor(FieldDescriptor descriptor)
    {
        if (string.Equals(descriptor.Kind, "bool", StringComparison.OrdinalIgnoreCase))
        {
            var check = new CheckBox
            {
                Content = "Bật / Tắt",
                Foreground = new SolidColorBrush(Color.Parse("#DCE8F4"))
            };
            check.Click += (_, _) => EditorValueChanged(descriptor, check);
            return check;
        }

        if (string.Equals(descriptor.Kind, "enum", StringComparison.OrdinalIgnoreCase))
        {
            var combo = new ComboBox
            {
                ItemsSource = descriptor.EnumValues,
                MinHeight = 34
            };
            combo.SelectionChanged += (_, _) => EditorValueChanged(descriptor, combo);
            return combo;
        }

        var text = new TextBox
        {
            MinHeight = 34,
            Watermark = descriptor.Kind switch
            {
                "int" => "Số nguyên",
                "float" => "Số",
                "time" => "HH:MM",
                _ => "Giá trị"
            }
        };
        text.TextChanged += (_, _) => EditorValueChanged(descriptor, text);
        return text;
    }

    private void EditorValueChanged(FieldDescriptor descriptor, Control editor)
    {
        if (_suppressChanges || _draft is null || descriptor.LockedValue is not null)
            return;

        JsonNode? value = editor switch
        {
            CheckBox check => JsonValue.Create(check.IsChecked == true),
            ComboBox combo => JsonValue.Create(combo.SelectedItem?.ToString() ?? string.Empty),
            TextBox text => JsonValue.Create(text.Text ?? string.Empty),
            _ => null
        };

        SetDraftValue(descriptor.Path, value);
        _dirty = true;
        UpdateDirtyStatus();
        UpdateQuickValues();
        this.FindControl<TextBlock>("ValidationStateText")!.Text = "NOT VALIDATED";
        this.FindControl<TextBlock>("ValidationStateText")!.Foreground = Brushes.Gold;
    }

    private void LoadDraft(JsonElement profile, bool dirty)
    {
        var parsed = JsonNode.Parse(profile.GetRawText()) as JsonObject
            ?? throw new InvalidDataException("Profile root must be an object.");

        _draft = parsed;
        _suppressChanges = true;

        try
        {
            foreach (var binding in _fields)
            {
                var value = GetDraftValue(binding.Descriptor.Path);
                SetEditorValue(binding.Editor, binding.Descriptor, value);
            }
        }
        finally
        {
            _suppressChanges = false;
        }

        _dirty = dirty;
        UpdateDirtyStatus();
        UpdateQuickValues();
        this.FindControl<TextBlock>("ValidationStateText")!.Text = "NOT VALIDATED";
        this.FindControl<TextBlock>("ValidationStateText")!.Foreground = Brushes.Gold;
    }

    private static void SetEditorValue(Control editor, FieldDescriptor descriptor, JsonNode? value)
    {
        if (editor is CheckBox check)
        {
            bool parsed = false;
            if (value is JsonValue jsonValue && jsonValue.TryGetValue<bool>(out var boolValue))
                parsed = boolValue;
            check.IsChecked = parsed;
            return;
        }

        if (editor is ComboBox combo)
        {
            string current = value?.ToString() ?? string.Empty;
            combo.SelectedItem = descriptor.EnumValues.FirstOrDefault(
                item => string.Equals(item, current, StringComparison.OrdinalIgnoreCase));
            return;
        }

        if (editor is TextBox text)
            text.Text = value?.ToString() ?? string.Empty;
    }

    private void UpdateQuickValues()
    {
        if (_draft is null)
            return;

        this.FindControl<TextBlock>("ProfileNameText")!.Text =
            $"Profile: {GetDraftValue("profile.name")?.ToString() ?? "—"}";
        this.FindControl<TextBlock>("DirectionQuickValue")!.Text =
            GetDraftValue("timeframes.direction")?.ToString() ?? "—";
        this.FindControl<TextBlock>("PullbackQuickValue")!.Text =
            GetDraftValue("timeframes.pullback")?.ToString() ?? "—";
        this.FindControl<TextBlock>("TriggerQuickValue")!.Text =
            GetDraftValue("timeframes.trigger")?.ToString() ?? "—";
    }

    private void UpdateDirtyStatus()
    {
        var text = this.FindControl<TextBlock>("DirtyStateText")!;
        text.Text = _dirty ? "UNSAVED CHANGES" : "UNCHANGED";
        text.Foreground = _dirty ? Brushes.Gold : Brushes.LightGreen;
    }

    private async void Defaults_OnClick(object? sender, RoutedEventArgs e)
    {
        await RunUiActionAsync(async () =>
        {
            EnsureSupervisorReady();
            var profile = await _supervisor!.GetDefaultConfigAsync();
            LoadDraft(profile, dirty: true);
            SetStatus("Đã nạp mặc định canonical. Bấm Áp dụng Active để dùng trong Engine.", Brushes.LightGreen);
        });
    }

    private async void ReloadActive_OnClick(object? sender, RoutedEventArgs e)
    {
        await RunUiActionAsync(async () =>
        {
            EnsureSupervisorReady();
            var profile = await _supervisor!.GetActiveConfigAsync();
            LoadDraft(profile, dirty: false);
            SetStatus("Đã hoàn tác draft về active profile hiện tại của Engine.", Brushes.LightGreen);
        });
    }

    private async void Validate_OnClick(object? sender, RoutedEventArgs e)
    {
        await RunUiActionAsync(async () =>
        {
            var result = await ValidateDraftAsync();
            if (result.Valid)
                SetStatus("Cấu hình hợp lệ. Không có safety/range lỗi.", Brushes.LightGreen);
            else
                ShowValidationErrors(result.Errors);
        });
    }

    private async void Apply_OnClick(object? sender, RoutedEventArgs e)
    {
        await RunUiActionAsync(async () =>
        {
            EnsureSupervisorReady();
            var validation = await ValidateDraftAsync();
            if (!validation.Valid || validation.Profile is null)
            {
                ShowValidationErrors(validation.Errors);
                return;
            }

            var apply = await _supervisor!.ApplyActiveConfigAsync(validation.Profile.Value);
            if (!apply.Applied || apply.Profile is null)
            {
                ShowValidationErrors(apply.Errors);
                return;
            }

            LoadDraft(apply.Profile.Value, dirty: false);
            this.FindControl<TextBlock>("ValidationStateText")!.Text = "VALID + ACTIVE";
            this.FindControl<TextBlock>("ValidationStateText")!.Foreground = Brushes.LightGreen;
            SetStatus("Active profile đã được Python Engine xác thực và áp dụng. Execution vẫn khóa.", Brushes.LightGreen);
        });
    }

    private async void LoadJson_OnClick(object? sender, RoutedEventArgs e)
    {
        await RunUiActionAsync(async () =>
        {
            var storage = RequireStorageProvider();
            var files = await storage.OpenFilePickerAsync(new FilePickerOpenOptions
            {
                Title = "Mở XAUPY profile JSON",
                AllowMultiple = false,
                FileTypeFilter = new[] { JsonFileType }
            });

            var file = files.FirstOrDefault();
            if (file is null)
                return;

            await using var stream = await file.OpenReadAsync();
            using var document = await JsonDocument.ParseAsync(stream);
            if (document.RootElement.ValueKind != JsonValueKind.Object)
                throw new InvalidDataException("JSON root phải là object.");

            EnsureSupervisorReady();
            var validation = await _supervisor!.ValidateConfigAsync(document.RootElement.Clone());
            if (!validation.Valid || validation.Profile is null)
            {
                ShowValidationErrors(validation.Errors);
                return;
            }

            LoadDraft(validation.Profile.Value, dirty: true);
            _lastSetTemplatePath = null;
            SetStatus($"Đã mở JSON: {file.Name}. Draft chưa được Apply.", Brushes.LightGreen);
        });
    }

    private async void SaveJson_OnClick(object? sender, RoutedEventArgs e)
    {
        await RunUiActionAsync(async () =>
        {
            var validation = await ValidateDraftAsync();
            if (!validation.Valid || validation.Profile is null)
            {
                ShowValidationErrors(validation.Errors);
                return;
            }

            var storage = RequireStorageProvider();
            var file = await storage.SaveFilePickerAsync(new FilePickerSaveOptions
            {
                Title = "Lưu XAUPY profile JSON",
                SuggestedFileName = SuggestedProfileFileName(),
                DefaultExtension = "json",
                FileTypeChoices = new[] { JsonFileType }
            });

            if (file is null)
                return;

            await using var stream = await file.OpenWriteAsync();
            if (stream.CanSeek)
                stream.SetLength(0);

            await JsonSerializer.SerializeAsync(
                stream,
                validation.Profile.Value,
                new JsonSerializerOptions { WriteIndented = true });
            await stream.FlushAsync();

            SetStatus($"Đã lưu profile JSON: {file.Name}.", Brushes.LightGreen);
        });
    }

    private async void ImportSet_OnClick(object? sender, RoutedEventArgs e)
    {
        await RunUiActionAsync(async () =>
        {
            EnsureConfigToolExists();

            var storage = RequireStorageProvider();
            var files = await storage.OpenFilePickerAsync(new FilePickerOpenOptions
            {
                Title = "Nhập preset MT5 .set",
                AllowMultiple = false,
                FileTypeFilter = new[] { SetFileType }
            });

            var file = files.FirstOrDefault();
            if (file is null)
                return;

            string inputPath = file.Path.LocalPath;
            var validation = await ValidateDraftAsync();
            if (!validation.Valid || validation.Profile is null)
            {
                ShowValidationErrors(validation.Errors);
                return;
            }

            string tempRoot = CreateTempDirectory();
            try
            {
                string baseProfile = Path.Combine(tempRoot, "base.json");
                string outputProfile = Path.Combine(tempRoot, "imported.json");
                string reportPath = Path.Combine(tempRoot, "report.json");

                await File.WriteAllTextAsync(
                    baseProfile,
                    JsonSerializer.Serialize(
                        validation.Profile.Value,
                        new JsonSerializerOptions { WriteIndented = true }),
                    Encoding.UTF8);

                var result = await RunConfigToolAsync(new[]
                {
                    "import-set",
                    inputPath,
                    "--base-profile", baseProfile,
                    "--out", outputProfile,
                    "--report", reportPath
                });

                if (result.ExitCode != 0)
                    throw new InvalidOperationException($"xaupy-config import-set failed: {result.StandardError}");

                using var importedDocument = JsonDocument.Parse(await File.ReadAllTextAsync(outputProfile));
                EnsureSupervisorReady();
                var importedValidation = await _supervisor!.ValidateConfigAsync(importedDocument.RootElement.Clone());

                if (!importedValidation.Valid || importedValidation.Profile is null)
                {
                    ShowValidationErrors(importedValidation.Errors);
                    return;
                }

                int unknownCount = 0;
                if (File.Exists(reportPath))
                {
                    using var report = JsonDocument.Parse(await File.ReadAllTextAsync(reportPath));
                    if (report.RootElement.TryGetProperty("unknown_count", out var unknown) &&
                        unknown.TryGetInt32(out var count))
                    {
                        unknownCount = count;
                    }
                }

                LoadDraft(importedValidation.Profile.Value, dirty: true);
                _lastSetTemplatePath = inputPath;
                SetStatus(
                    $"Đã nhập {file.Name}. Unknown/preserved keys: {unknownCount}. Xuất .set sẽ dùng file này làm template.",
                    Brushes.LightGreen);
            }
            finally
            {
                TryDeleteDirectory(tempRoot);
            }
        });
    }

    private async void ExportSet_OnClick(object? sender, RoutedEventArgs e)
    {
        await RunUiActionAsync(async () =>
        {
            EnsureConfigToolExists();

            var validation = await ValidateDraftAsync();
            if (!validation.Valid || validation.Profile is null)
            {
                ShowValidationErrors(validation.Errors);
                return;
            }

            var storage = RequireStorageProvider();
            var file = await storage.SaveFilePickerAsync(new FilePickerSaveOptions
            {
                Title = "Xuất MT5 .set",
                SuggestedFileName = Path.ChangeExtension(SuggestedProfileFileName(), ".set"),
                DefaultExtension = "set",
                FileTypeChoices = new[] { SetFileType }
            });

            if (file is null)
                return;

            string outputPath = file.Path.LocalPath;
            string tempRoot = CreateTempDirectory();

            try
            {
                string profilePath = Path.Combine(tempRoot, "profile.json");
                await File.WriteAllTextAsync(
                    profilePath,
                    JsonSerializer.Serialize(
                        validation.Profile.Value,
                        new JsonSerializerOptions { WriteIndented = true }),
                    Encoding.UTF8);

                var arguments = new List<string>
                {
                    "export-set",
                    profilePath
                };

                if (!string.IsNullOrWhiteSpace(_lastSetTemplatePath) &&
                    File.Exists(_lastSetTemplatePath))
                {
                    arguments.Add("--template");
                    arguments.Add(_lastSetTemplatePath);
                }

                arguments.Add("--out");
                arguments.Add(outputPath);

                var result = await RunConfigToolAsync(arguments);
                if (result.ExitCode != 0)
                    throw new InvalidOperationException($"xaupy-config export-set failed: {result.StandardError}");

                _lastSetTemplatePath = outputPath;
                SetStatus(
                    $"Đã xuất {file.Name}" +
                    (arguments.Contains("--template") ? " theo template đã nhập." : " dạng canonical UTF-16LE."),
                    Brushes.LightGreen);
            }
            finally
            {
                TryDeleteDirectory(tempRoot);
            }
        });
    }

    private async Task<ConfigValidationResult> ValidateDraftAsync()
    {
        EnsureSupervisorReady();

        if (_draft is null)
            throw new InvalidOperationException("Draft profile chưa được tải.");

        JsonElement element = JsonSerializer.SerializeToElement(_draft);
        var result = await _supervisor!.ValidateConfigAsync(element);

        var state = this.FindControl<TextBlock>("ValidationStateText")!;
        state.Text = result.Valid ? "VALID" : $"INVALID ({result.Errors.Count})";
        state.Foreground = result.Valid ? Brushes.LightGreen : Brushes.IndianRed;

        return result;
    }

    private void ShowValidationErrors(IReadOnlyList<string> errors)
    {
        string detail = errors.Count == 0
            ? "Cấu hình không hợp lệ."
            : string.Join(" • ", errors.Take(6)) +
              (errors.Count > 6 ? $" • ... +{errors.Count - 6} lỗi" : string.Empty);

        SetStatus(detail, Brushes.IndianRed);
    }

    private async Task RunUiActionAsync(Func<Task> action)
    {
        if (_loading)
            return;

        _loading = true;
        try
        {
            await action();
        }
        catch (Exception ex)
        {
            SetStatus(ex.Message, Brushes.IndianRed);
        }
        finally
        {
            _loading = false;
        }
    }

    private void SearchBox_OnTextChanged(object? sender, TextChangedEventArgs e)
    {
        ApplySearchFilter();
    }

    private void ApplySearchFilter()
    {
        string query = this.FindControl<TextBox>("SearchBox")?.Text?.Trim().ToLowerInvariant()
                       ?? string.Empty;
        int visible = 0;

        foreach (var field in _fields)
        {
            string haystack =
                $"{field.Descriptor.Path} {field.Descriptor.SetKey} {field.Descriptor.Description} {field.GroupKey}"
                    .ToLowerInvariant();

            bool show = string.IsNullOrEmpty(query) || haystack.Contains(query, StringComparison.Ordinal);
            field.Row.IsVisible = show;
            if (show)
                visible++;
        }

        foreach (var group in _groups.Values)
            group.Card.IsVisible = group.Fields.Any(field => field.Row.IsVisible);

        var countText = this.FindControl<TextBlock>("VisibleCountText");
        if (countText is not null)
            countText.Text = $"{visible} / {_fields.Count}";
    }

    private void SetDraftValue(string path, JsonNode? value)
    {
        if (_draft is null)
            return;

        string[] parts = path.Split('.');
        JsonObject current = _draft;

        for (int i = 0; i < parts.Length - 1; i++)
        {
            if (current[parts[i]] is not JsonObject child)
            {
                child = new JsonObject();
                current[parts[i]] = child;
            }

            current = child;
        }

        current[parts[^1]] = value;
    }

    private JsonNode? GetDraftValue(string path)
    {
        JsonNode? current = _draft;

        foreach (var part in path.Split('.'))
        {
            if (current is not JsonObject obj)
                return null;
            current = obj[part];
        }

        return current;
    }

    private static string GroupKey(string path)
    {
        if (path.StartsWith("filters.adx.", StringComparison.Ordinal))
            return "filters.adx";
        if (path.StartsWith("filters.atr.", StringComparison.Ordinal))
            return "filters.atr";
        if (path.StartsWith("filters.open.", StringComparison.Ordinal))
            return "filters.open";
        if (path.StartsWith("take_profit.dynamic.", StringComparison.Ordinal))
            return "take_profit.dynamic";

        int dot = path.IndexOf('.');
        return dot > 0 ? path[..dot] : path;
    }

    private static (int Order, string Title) GroupTitle(string key)
    {
        return GroupTitles.TryGetValue(key, out var value)
            ? value
            : (999, key);
    }

    private static string BoundsText(FieldDescriptor descriptor)
    {
        if (descriptor.EnumValues.Count > 0)
            return $"{descriptor.EnumValues.Count} lựa chọn";

        if (descriptor.Minimum is not null && descriptor.Maximum is not null)
            return $"Min {descriptor.Minimum:g} • Max {descriptor.Maximum:g}";

        if (descriptor.Minimum is not null)
            return $"Min {descriptor.Minimum:g}";

        if (descriptor.Maximum is not null)
            return $"Max {descriptor.Maximum:g}";

        return string.Empty;
    }

    private void EnsureSupervisorReady()
    {
        if (_supervisor is null)
            throw new InvalidOperationException("Configuration editor chưa gắn Engine supervisor.");

        if (_supervisor.State != EngineConnectionState.Ready)
            throw new InvalidOperationException("Python Engine chưa READY.");
    }

    private IStorageProvider RequireStorageProvider()
    {
        var top = TopLevel.GetTopLevel(this)
                  ?? throw new InvalidOperationException("Không tìm thấy TopLevel.");

        if (!top.StorageProvider.CanOpen || !top.StorageProvider.CanSave)
            throw new InvalidOperationException("Storage provider không hỗ trợ open/save file.");

        return top.StorageProvider;
    }

    private string ConfigToolPath =>
        Path.Combine(
            AppContext.BaseDirectory,
            "tools",
            OperatingSystem.IsWindows() ? "xaupy-config.exe" : "xaupy-config");

    private void EnsureConfigToolExists()
    {
        if (!File.Exists(ConfigToolPath))
            throw new FileNotFoundException(
                "Không tìm thấy tools/xaupy-config.exe. Hãy dùng full Task 006 build.",
                ConfigToolPath);
    }

    private async Task<(int ExitCode, string StandardOutput, string StandardError)> RunConfigToolAsync(
        IEnumerable<string> arguments)
    {
        var startInfo = new ProcessStartInfo
        {
            FileName = ConfigToolPath,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true
        };

        foreach (var argument in arguments)
            startInfo.ArgumentList.Add(argument);

        using var process = Process.Start(startInfo)
            ?? throw new InvalidOperationException("Không thể khởi động xaupy-config.");

        string stdout = await process.StandardOutput.ReadToEndAsync();
        string stderr = await process.StandardError.ReadToEndAsync();
        await process.WaitForExitAsync();

        return (process.ExitCode, stdout, stderr);
    }

    private static string CreateTempDirectory()
    {
        string path = Path.Combine(Path.GetTempPath(), "XAUPY", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(path);
        return path;
    }

    private static void TryDeleteDirectory(string path)
    {
        try
        {
            if (Directory.Exists(path))
                Directory.Delete(path, recursive: true);
        }
        catch
        {
        }
    }

    private string SuggestedProfileFileName()
    {
        string name = GetDraftValue("profile.name")?.ToString() ?? "XAUPY_Profile";
        foreach (char invalid in Path.GetInvalidFileNameChars())
            name = name.Replace(invalid, '_');

        if (string.IsNullOrWhiteSpace(name))
            name = "XAUPY_Profile";

        return name + ".json";
    }

    private void SetStatus(string text, IBrush color)
    {
        var status = this.FindControl<TextBlock>("StatusText");
        if (status is null)
            return;

        status.Text = text;
        status.Foreground = color;
    }

    private static string ReadRequiredString(JsonElement parent, string name)
    {
        return ReadOptionalString(parent, name)
               ?? throw new InvalidDataException($"Schema field missing {name}.");
    }

    private static string? ReadOptionalString(JsonElement parent, string name)
    {
        return parent.TryGetProperty(name, out var value) &&
               value.ValueKind == JsonValueKind.String
            ? value.GetString()
            : null;
    }

    private static double? TryReadNullableDouble(JsonElement parent, string name)
    {
        if (!parent.TryGetProperty(name, out var value) ||
            value.ValueKind == JsonValueKind.Null ||
            value.ValueKind == JsonValueKind.Undefined)
        {
            return null;
        }

        return value.ValueKind == JsonValueKind.Number && value.TryGetDouble(out var number)
            ? number
            : null;
    }
}
