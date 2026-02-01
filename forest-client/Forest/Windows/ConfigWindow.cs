using Dalamud.Bindings.ImGui; // API 13 ImGui bindings
using Dalamud.Interface.Windowing;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Numerics;
using Forest.Features.Venues;
using ImGuiCond = Dalamud.Bindings.ImGui.ImGuiCond;
using ImGuiWindowFlags = Dalamud.Bindings.ImGui.ImGuiWindowFlags;

namespace Forest.Windows;

public class ConfigWindow : Window, IDisposable
{
    private readonly Plugin Plugin;
    private ForestConfig Configuration;
    private bool _connecting = false;
    private bool _confirmDelete = false;
    private List<Venue> _availableVenues = new();
    private bool _venuesLoading = false;
    private int _selectedVenueIndex = -1;

    public ConfigWindow(Plugin plugin) : base("Forest Settings###ForestConfigWindow")
    {
        Flags = ImGuiWindowFlags.NoCollapse | ImGuiWindowFlags.NoScrollbar | ImGuiWindowFlags.NoScrollWithMouse;
        Size = new Vector2(500, 420);
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
        ImGui.TextDisabled("Venue & Events");
        if (Plugin.Config.CurrentVenueId.HasValue && !string.IsNullOrWhiteSpace(Plugin.Config.CurrentVenueName))
        {
            ImGui.TextColored(new Vector4(0.5f, 1f, 0.6f, 1f), $"Current venue: {Plugin.Config.CurrentVenueName}");
        }
        else
        {
            ImGui.TextDisabled("No venue assigned");
        }

        if (Plugin.Config.BingoConnected && Plugin.VenuesApi != null)
        {
            if (_availableVenues.Count == 0)
            {
                if (!_venuesLoading && ImGui.Button("Load Venues"))
                {
                    _venuesLoading = true;
                    _ = LoadVenuesAsync();
                }
                if (_venuesLoading)
                    ImGui.TextDisabled("Loading venues...");
            }
            else
            {
                var venueNames = _availableVenues.Select(v => v.Name).ToArray();
                ImGui.SetNextItemWidth(360);
                if (ImGui.Combo("Select Venue", ref _selectedVenueIndex, venueNames, venueNames.Length))
                {
                    if (_selectedVenueIndex >= 0 && _selectedVenueIndex < _availableVenues.Count)
                    {
                        var venue = _availableVenues[_selectedVenueIndex];
                        Plugin.Config.CurrentVenueId = venue.Id;
                        Plugin.Config.CurrentVenueName = venue.Name;
                        Plugin.Config.VenueLastFetched = DateTime.UtcNow;
                        Plugin.Config.Save();
                        Plugin.ChatGui.Print($"[Forest] Venue set to: {venue.Name}");
                    }
                }
            }
        }
        else
        {
            ImGui.TextDisabled("Connect to server to manage venues.");
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

    private async System.Threading.Tasks.Task LoadVenuesAsync()
    {
        try
        {
            if (Plugin.VenuesApi != null)
            {
                _availableVenues = await Plugin.VenuesApi.ListVenuesAsync();
                if (Plugin.Config.CurrentVenueId.HasValue)
                {
                    for (int i = 0; i < _availableVenues.Count; i++)
                    {
                        if (_availableVenues[i].Id == Plugin.Config.CurrentVenueId.Value)
                        {
                            _selectedVenueIndex = i;
                            break;
                        }
                    }
                }
            }
        }
        catch (Exception ex)
        {
            Plugin.Log?.Error(ex, "Failed to load venues");
        }
        finally
        {
            _venuesLoading = false;
        }
    }

}

