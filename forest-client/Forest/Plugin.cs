using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Threading.Tasks;

using Dalamud.Game.Command;
using Dalamud.Interface.Windowing;
using Dalamud.IoC;
using Dalamud.Plugin;
using Dalamud.Plugin.Services;

using Forest.Windows;

namespace Forest;

public sealed class Plugin : IDalamudPlugin
{
    [PluginService] internal static IDalamudPluginInterface PluginInterface { get; private set; } = null!;
    [PluginService] internal static ITextureProvider TextureProvider { get; private set; } = null!;
    [PluginService] internal static ICommandManager CommandManager { get; private set; } = null!;
    [PluginService] internal static IClientState ClientState { get; private set; } = null!;
    [PluginService] internal static IDataManager DataManager { get; private set; } = null!;
    [PluginService] internal static IPluginLog Log { get; private set; } = null!;
    [PluginService] internal static IObjectTable ObjectTable { get; private set; } = null!;
    [PluginService] internal static IFramework Framework { get; private set; } = null!;
    [PluginService] internal static IChatGui ChatGui { get; private set; } = null!;
    [PluginService] internal static IContextMenu ContextMenu { get; private set; } = null!;

    private const string CommandName = "/forest";

    public ForestConfig Config { get; init; }
    public readonly WindowSystem WindowSystem = new("ForestPlugin");

    private ConfigWindow ConfigWindow { get; init; }
    private MainWindow MainWindow { get; init; }

    public Plugin(IDalamudPluginInterface pluginInterface)
    {
        // Load config
        Config = ForestConfig.LoadConfig(PluginInterface);

        // Ensure a stable AdminClientId once
        if (string.IsNullOrWhiteSpace(Config.AdminClientId))
        {
            Config.AdminClientId = Guid.NewGuid().ToString("D");
            try { Config.Save(); } catch { /* ignore */ }
            Log.Information($"Generated AdminClientId: {Config.AdminClientId}");
        }

        ConfigWindow = new ConfigWindow(this);
        MainWindow = new MainWindow(this);

        WindowSystem.AddWindow(ConfigWindow);
        WindowSystem.AddWindow(MainWindow);


        CommandManager.AddHandler(CommandName, new CommandInfo(OnCommand)
        {
            HelpMessage = "Open Forest UI"
        });

        pluginInterface.UiBuilder.Draw += DrawUI;
        pluginInterface.UiBuilder.OpenConfigUi += ToggleConfigUI;
        pluginInterface.UiBuilder.OpenMainUi += ToggleMainUI;

        Log.Information($"Loaded {pluginInterface.Manifest.Name} {pluginInterface.Manifest.AssemblyVersion}");

        if (!string.IsNullOrWhiteSpace(Config.BingoApiKey))
        {
            _ = ConnectToServerAsync();
        }
    }

    public void Dispose()
    {
        WindowSystem.RemoveAllWindows();

        ConfigWindow.Dispose();
        MainWindow.Dispose();

        CommandManager.RemoveHandler(CommandName);
    }

    private void OnCommand(string command, string args) => ToggleMainUI();

    private void DrawUI() => WindowSystem.Draw();

    public void ToggleConfigUI() => ConfigWindow.Toggle();
    public void ToggleMainUI() => MainWindow.Toggle();


    // -------------------- Connect / Announce --------------------

    public async Task<bool> ConnectToServerAsync()
    {
        var baseUrl = Config.BingoApiBaseUrl?.Trim();
        var apiKey = Config.BingoApiKey?.Trim();

        if (string.IsNullOrWhiteSpace(baseUrl))
        {
            ChatGui.PrintError("[Forest] Bingo Base URL is empty in settings.");
            SetConn(false, "No URL");
            return false;
        }
        if (string.IsNullOrWhiteSpace(apiKey))
        {
            ChatGui.PrintError("[Forest] Auth token is empty in settings.");
            SetConn(false, "No auth");
            return false;
        }

        try
        {
            using var http = new HttpClient();
            http.Timeout = TimeSpan.FromSeconds(10);

            http.DefaultRequestHeaders.Add("X-API-Key", apiKey);

            // 1) Health
            var healthUrl = baseUrl.TrimEnd('/') + "/healthz";
            using (var health = await http.GetAsync(healthUrl).ConfigureAwait(false))
            {
                var body = await health.Content.ReadAsStringAsync().ConfigureAwait(false);
                if (!health.IsSuccessStatusCode)
                {
                    Log.Warning($"Health {health.StatusCode}: {body}");
                    ChatGui.PrintError($"[Forest] Health check failed: {health.StatusCode}");
                    SetConn(false, $"HTTP {health.StatusCode}");
                    return false;
                }

                // Optional: record a tidbit for display
                Config.BingoServerInfo = $"OK {health.StatusCode}";
            }

            // 2) Auth check via bingo list
            var listUrl = baseUrl.TrimEnd('/') + "/bingo/games";
            using (var resp = await http.GetAsync(listUrl).ConfigureAwait(false))
            {
                var respBody = await resp.Content.ReadAsStringAsync().ConfigureAwait(false);
                if (!resp.IsSuccessStatusCode)
                {
                    Log.Warning($"List games HTTP {resp.StatusCode}: {respBody}");
                    ChatGui.PrintError($"[Forest] Auth failed: {resp.StatusCode}");
                    SetConn(false, $"HTTP {resp.StatusCode}");
                    return false;
                }
            }

            SetConn(true, "connected");
            ChatGui.Print("[Forest] Connected to Bingo server.");
            return true;
        }
        catch (Exception ex)
        {
            Log.Error(ex, "ConnectToServerAsync failed");
            ChatGui.PrintError($"[Forest] Connect failed: {ex.Message}");
            SetConn(false, ex.GetType().Name);
            return false;
        }

        void SetConn(bool connected, string info)
        {
            Config.BingoConnected = connected;
            Config.BingoLastConnectedUtc = connected ? DateTime.UtcNow : Config.BingoLastConnectedUtc;
            Config.BingoServerInfo = info;
            try { Config.Save(); } catch { /* ignore */ }
        }
    }
}
