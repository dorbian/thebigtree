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
        var publicBase = Plugin.Config.CardgamesPublicBaseUrl ?? "https://rites.thebigtree.life";
        ImGui.SetNextItemWidth(360);
        if (ImGui.InputText("Cardgames Public URL", ref publicBase, 512))
        {
            Plugin.Config.CardgamesPublicBaseUrl = string.IsNullOrWhiteSpace(publicBase) ? null : publicBase.Trim();
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
    }
}

