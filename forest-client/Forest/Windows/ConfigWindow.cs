using Dalamud.Bindings.ImGui; // API 13 ImGui bindings
using Dalamud.Interface.Windowing;
using System;
using System.Numerics;
using ImGuiCond = Dalamud.Bindings.ImGui.ImGuiCond;
using ImGuiWindowFlags = Dalamud.Bindings.ImGui.ImGuiWindowFlags;

namespace Forest.Windows;

public class ConfigWindow : Window, IDisposable
{
    private readonly Plugin Plugin;
    private ForestConfig Configuration;
    private bool _connecting = false;
    private bool _confirmDelete = false;

    public ConfigWindow(Plugin plugin) : base("Forest Settings###ForestConfigWindow")
    {
        Flags = ImGuiWindowFlags.NoCollapse | ImGuiWindowFlags.NoScrollbar | ImGuiWindowFlags.NoScrollWithMouse;
        Size = new Vector2(500, 260);
        SizeCondition = ImGuiCond.FirstUseEver;

        Plugin = plugin;
        Configuration = plugin.Config;
    }

    public void Dispose() { }

    public override void PreDraw()
    {
        Flags &= ~ImGuiWindowFlags.NoMove;
    }

    public override void Draw()
    {
        // General (demo) settings kept minimal
        var lockCols = Configuration.IsConfigWindowMovable;
        if (ImGui.Checkbox("Lock session columns", ref lockCols))
        {
            Configuration.IsConfigWindowMovable = lockCols;
            Configuration.Save();
        }
        var disableNearby = Configuration.DisableNearbyScan;
        if (ImGui.Checkbox("Disable nearby player scan", ref disableNearby))
        {
            Configuration.DisableNearbyScan = disableNearby;
            Configuration.Save();
        }

        ImGui.Separator();
        ImGui.TextDisabled("Bingo Admin Connection");
        // Auth token
        var apiKey = Plugin.Config.BingoApiKey ?? "";
        ImGui.SetNextItemWidth(360);
        if (ImGui.InputText("Auth Token", ref apiKey, 512))
        {
            Plugin.Config.BingoApiKey = string.IsNullOrWhiteSpace(apiKey) ? null : apiKey.Trim();
            Plugin.Config.Save();
        }
        ImGui.Spacing();
        var publicBase = (Plugin.Config.CardgamesPublicBaseUrl ?? "https://rites.thebigtree.life").Trim();
        if (publicBase.StartsWith("https://", StringComparison.OrdinalIgnoreCase))
            publicBase = publicBase.Substring("https://".Length);
        else if (publicBase.StartsWith("http://", StringComparison.OrdinalIgnoreCase))
            publicBase = publicBase.Substring("http://".Length);
        ImGui.SetNextItemWidth(360);
        if (ImGui.InputText("Server", ref publicBase, 512))
        {
            var trimmed = publicBase.Trim();
            Plugin.Config.CardgamesPublicBaseUrl = string.IsNullOrWhiteSpace(trimmed)
                ? null
                : $"https://{trimmed}";
            Plugin.Config.Save();
        }
        ImGui.Spacing();
        // Connect / status
        if (!_connecting)
        {
            if (ImGui.Button("Reconnect"))
            {
                _connecting = true;
                _ = Plugin.ConnectToServerAsync().ContinueWith(_ =>
                {
                    _connecting = false;
                });
            }
        }
        else
        {
            ImGui.TextDisabled("Connecting...");
        }

        ImGui.SameLine();
        if (Plugin.Config.BingoConnected)
        {
            ImGui.TextColored(new Vector4(0.5f, 1f, 0.6f, 1f), "Connected");
            if (Plugin.Config.BingoLastConnectedUtc is DateTime dt)
            {
                ImGui.SameLine();
                ImGui.TextDisabled($"at {dt:yyyy-MM-dd HH:mm:ss} UTC");
            }
        }
        else
        {
            ImGui.TextColored(new Vector4(1f, 0.55f, 0.55f, 1f), "Not connected");
            if (!string.IsNullOrEmpty(Plugin.Config.BingoServerInfo))
            {
                ImGui.SameLine();
                ImGui.TextDisabled($"({Plugin.Config.BingoServerInfo})");
            }
        }

        ImGui.Separator();
        ImGui.TextDisabled("Danger zone");
        ImGui.TextWrapped("Delete all Forest plugin data on this machine.");
        if (ImGui.Button("Delete all plugin data"))
            _confirmDelete = true;
        if (_confirmDelete)
        {
            ImGui.OpenPopup("ConfirmDeleteData");
            _confirmDelete = false;
        }
        ImGui.SetNextWindowSize(new Vector2(420, 160), ImGuiCond.Appearing);
        if (ImGui.BeginPopupModal("ConfirmDeleteData"))
        {
            ImGui.TextWrapped("This will delete all Forest config files and local plugin data. This cannot be undone.");
            ImGui.Spacing();
            if (ImGui.Button("Delete now"))
            {
                try
                {
                    var configDir = Plugin.PluginInterface.GetPluginConfigDirectory();
                    if (System.IO.Directory.Exists(configDir))
                    {
                        System.IO.Directory.Delete(configDir, true);
                    }
                }
                catch (Exception ex)
                {
                    Plugin.Log?.Error($"Failed to delete plugin data: {ex.Message}");
                }
                ImGui.CloseCurrentPopup();
            }
            ImGui.SameLine();
            if (ImGui.Button("Cancel"))
                ImGui.CloseCurrentPopup();
            ImGui.EndPopup();
        }
    }
}

