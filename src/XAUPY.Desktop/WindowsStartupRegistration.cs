using Microsoft.Win32;

namespace XAUPY.Desktop;

public static class WindowsStartupRegistration
{
    private const string KeyPath = @"Software\Microsoft\Windows\CurrentVersion\Run";
    public static void Update(bool enabled, string? executable, string valueName = "XAUPY")
    {
        if (!OperatingSystem.IsWindows())
        {
            if (enabled) throw new PlatformNotSupportedException("Windows startup requires Windows.");
            return;
        }
        ValidateName(valueName);
        using var run = Registry.CurrentUser.CreateSubKey(KeyPath, true);
        if (!enabled) { run.DeleteValue(valueName, false); return; }
        if (executable is null || !Path.IsPathFullyQualified(executable) || !File.Exists(executable)
            || !Path.GetFileName(executable).Equals("XAUPY.Desktop.exe", StringComparison.OrdinalIgnoreCase)
            || executable.Contains('"') || executable.Contains('\n'))
            throw new InvalidOperationException("Open XAUPY.Desktop.exe to register Windows startup.");
        run.SetValue(valueName, $"\"{executable}\"", RegistryValueKind.String);
        if (run.GetValue(valueName) as string != $"\"{executable}\"")
            throw new IOException("Windows startup registration could not be verified.");
    }
    public static string? Read(string valueName = "XAUPY")
    {
        ValidateName(valueName);
        if (!OperatingSystem.IsWindows()) return null;
        using var run = Registry.CurrentUser.OpenSubKey(KeyPath);
        return run?.GetValue(valueName) as string;
    }
    private static void ValidateName(string valueName)
    {
        if (valueName != "XAUPY" && (!valueName.StartsWith("XAUPY.Acceptance.", StringComparison.Ordinal)
            || !Guid.TryParseExact(valueName[17..], "N", out _)))
            throw new ArgumentException("Invalid XAUPY startup value.");
    }
}
