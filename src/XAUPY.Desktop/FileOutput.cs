using System.Text;
using Avalonia.Platform.Storage;

namespace XAUPY.Desktop;

/// <summary>Atomic local exports. Encoding/serialization fails before replacing an old file.</summary>
public static class FileOutput
{
    public static Task WriteTextAsync(IStorageFile file, string text, CancellationToken cancellationToken = default) =>
        WriteBytesAsync(file, new UTF8Encoding(false).GetBytes(text), cancellationToken);

    public static async Task WriteBytesAsync(IStorageFile file, ReadOnlyMemory<byte> bytes, CancellationToken cancellationToken = default)
    {
        string? path = file.TryGetLocalPath();
        if (!string.IsNullOrWhiteSpace(path)) { await WriteLocalAsync(path, bytes, cancellationToken); return; }
        cancellationToken.ThrowIfCancellationRequested();
        await using var destination = await file.OpenWriteAsync();
        await destination.WriteAsync(bytes, cancellationToken);
        if (destination.CanSeek) destination.SetLength(destination.Position);
        await destination.FlushAsync(cancellationToken);
    }

    public static async Task CopyAsync(IStorageFile file, Stream source, CancellationToken cancellationToken = default)
    {
        string? path = file.TryGetLocalPath();
        if (!string.IsNullOrWhiteSpace(path))
        {
            await ReplaceLocalAsync(path, stream => source.CopyToAsync(stream, cancellationToken), cancellationToken);
            return;
        }
        // Non-local providers own their commit semantics. The caller supplies
        // an already complete temporary export, never a live-changing query.
        cancellationToken.ThrowIfCancellationRequested();
        await using var destination = await file.OpenWriteAsync();
        await source.CopyToAsync(destination, cancellationToken);
        if (destination.CanSeek) destination.SetLength(destination.Position);
        await destination.FlushAsync(cancellationToken);
    }

    public static Task WriteLocalAsync(string path, ReadOnlyMemory<byte> data, CancellationToken cancellationToken = default) =>
        ReplaceLocalAsync(path, stream => stream.WriteAsync(data, cancellationToken).AsTask(), cancellationToken);

    private static async Task ReplaceLocalAsync(string path, Func<Stream, Task> write, CancellationToken cancellationToken)
    {
        path = Path.GetFullPath(path);
        string directory = Path.GetDirectoryName(path) ?? throw new InvalidDataException("Đường dẫn lưu không hợp lệ.");
        if (!Directory.Exists(directory)) throw new DirectoryNotFoundException(directory);
        string temporary = Path.Combine(directory, "." + Path.GetFileName(path) + "." + Guid.NewGuid().ToString("N") + ".tmp");
        try
        {
            await using (var stream = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None, 65536, FileOptions.Asynchronous))
            {
                await write(stream);
                await stream.FlushAsync(cancellationToken);
                stream.Flush(flushToDisk: true);
            }
            cancellationToken.ThrowIfCancellationRequested();
            File.Move(temporary, path, overwrite: true);
        }
        finally
        {
            try { if (File.Exists(temporary)) File.Delete(temporary); }
            catch (IOException) { }
            catch (UnauthorizedAccessException) { }
        }
    }
}
