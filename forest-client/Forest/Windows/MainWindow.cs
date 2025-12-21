using Dalamud.Bindings.ImGui; // API 13 ImGui bindings
using Dalamud.Game.ClientState;
using Dalamud.Game.ClientState.Objects;
using Dalamud.Game.ClientState.Objects.SubKinds;
using Dalamud.Game.Text;
using Dalamud.Game.Text.SeStringHandling;
using Dalamud.Interface.Utility.Raii;
using Dalamud.Interface.Textures;
using Dalamud.Interface.Windowing;
using Dalamud.Plugin.Services;

using Forest.Features.BingoAdmin;

using System;
using System.Collections.Generic;
using System.Linq;
using System.Numerics;
using System.IO;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using System.Text.RegularExpressions;

using ImGuiWindowFlags = Dalamud.Bindings.ImGui.ImGuiWindowFlags;

namespace Forest.Windows;

public class MainWindow : Window, IDisposable
{
    private readonly Plugin Plugin;

    // ---------- View switch ----------
    private enum View { Home, Hunt, MurderMystery, Bingo, Raffle, SpinWheel, Glam }
    private View _view = View.Home;

    // ---------- Left pane layout ----------
    private float _leftPaneWidth = 360f;   // resize via slider (stable with API 13 Columns)
    private float _leftSplitRatio = 0.60f; // Players(top) / Saved(bottom)
    private const float SplitterThickness = 6f;
    private const float SplitterMinTop = 120f;
    private const float SplitterMinBottom = 120f;

    // ---------- Players (nearby, live) ----------
    private string[] _nearbyPlayers = Array.Empty<string>();
    private string? _selectedOwner;

    // ---------- Bingo (list) ----------
    private List<BingoGame> _bingoGames = new();
    private bool _bingoGamesLoading = false;

    // ---------- Old ForestWindow state brought in ----------
    private DateTime _lastRefreshTime = DateTime.MinValue;
    private readonly DateTime _pluginStartTime;
    private DateTime? _votingStartTime = null;
    private readonly TimeSpan _votingDuration = TimeSpan.FromMinutes(5);

    private readonly Dictionary<string, string> _receivedWhispers = new();
    private readonly HashSet<string> _whispersProcessed = new();

    // ---------- Bingo (Admin) ----------
    private BingoAdminApiClient? _bingoApi;
    private CancellationTokenSource? _bingoCts;
    private string _bingoStatus = "";
    private bool _bingoLoading = false;
    private string _bingoGameId = "";
    private GameStateEnvelope? _bingoState;
    private readonly Dictionary<string, List<CardInfo>> _bingoOwnerCards = new();
    private List<OwnerSummary> _bingoOwners = new();
    private string _bingoManualOwner = "";
    private const int BingoRandomMax = 40;
    private int _bingoRollAttempts = 0;
    private bool _bingoShowBuyLink = false;
    private string _bingoBuyLink = "";
    private string _bingoBuyOwner = "";
    private ISharedImmediateTexture? _homeIconTexture;
    private string? _homeIconPath;
    private string _raffleStatus = "";
    private string _wheelStatus = "";
    private string _glamStatus = "";

    public MainWindow(Plugin plugin)
        : base("Forest Manager##Main", ImGuiWindowFlags.NoScrollbar | ImGuiWindowFlags.NoScrollWithMouse | ImGuiWindowFlags.MenuBar)
    {
        Plugin = plugin;
        var baseDir = Forest.Plugin.PluginInterface.AssemblyLocation.DirectoryName ?? string.Empty;
        _homeIconPath = Path.Combine(baseDir, "Resources", "icon.png");
        if (File.Exists(_homeIconPath))
            _homeIconTexture = Forest.Plugin.TextureProvider.GetFromFile(_homeIconPath);
        _pluginStartTime = DateTime.UtcNow;

        SizeConstraints = new WindowSizeConstraints
        {
            MinimumSize = new Vector2(900, 560),
            MaximumSize = new Vector2(float.MaxValue, float.MaxValue)
        };

        // Hook timers & chat like the old ForestWindow
        Plugin.Framework.Update += OnFrameworkUpdate;
        Plugin.ChatGui.ChatMessage += OnChatMessage;
    }

    public void Dispose()
    {
        Plugin.Framework.Update -= OnFrameworkUpdate;
        Plugin.ChatGui.ChatMessage -= OnChatMessage;

        _bingoCts?.Cancel();
        _bingoApi?.Dispose();
    }

    // ------------------ Bingo: list/refresh ------------------
    private async Task Bingo_LoadGames()
    {
        Bingo_EnsureClient();
        _bingoGamesLoading = true;
        try
        {
            var list = await _bingoApi!.ListGamesAsync();
            _bingoGames = list ?? new();
            _bingoStatus = $"Loaded {_bingoGames.Count} game(s).";
        }
        catch (Exception ex)
        {
            _bingoStatus = $"Failed to load games: {ex.Message}";
            _bingoGames = new();
        }
        finally
        {
            _bingoGamesLoading = false;
        }
    }

    // ========================= CHAT / TIMER FROM OLD WINDOW =========================
    private void OnChatMessage(XivChatType type, int timestamp, ref SeString sender, ref SeString message, ref bool isHandled)
    {
        var allowManualRoll = _view == View.Bingo
            && _bingoState is not null
            && _bingoState.game.started
            && _bingoState.game.active
            && Plugin.Config.BingoConnected;
        if (allowManualRoll && TryHandleBingoRandom(sender.TextValue, message.TextValue))
            return;

        if (Raffle_HandleChatJoin(type, sender.TextValue, message.TextValue))
            return;

        if (Glam_HandleVote(type, sender.TextValue, message.TextValue))
            return;
        if (type != XivChatType.TellIncoming || !_votingStartTime.HasValue || Plugin.Config.CurrentGame == null)
            return;

        string senderName = sender.TextValue;
        string messageText = message.TextValue;

        // Only active players (not killer)
        if (!Plugin.Config.CurrentGame.ActivePlayers.Contains(senderName) ||
            senderName == Plugin.Config.CurrentGame.Killer)
            return;

        if (_receivedWhispers.ContainsKey(senderName))
            return;

        _receivedWhispers[senderName] = messageText;
        Plugin.Log?.Information($"[MurderMystery] Captured whisper from {senderName}: {messageText}");
    }

    private void OnFrameworkUpdate(IFramework _)
    {
        // warmup
        if ((DateTime.UtcNow - _pluginStartTime).TotalSeconds < 5) return;
        if (!Plugin.ClientState.IsLoggedIn || Plugin.ClientState.LocalPlayer == null) return;

        CheckVotingPeriod();
        CheckCountdownCompletion();

        if ((DateTime.UtcNow - _lastRefreshTime).TotalSeconds < 10) return;
        _lastRefreshTime = DateTime.UtcNow;

        Raffle_CheckAutoClose();

        // nearby players (live)
        _nearbyPlayers = Plugin.ObjectTable
            .Where(o => o is IPlayerCharacter)
            .Cast<IPlayerCharacter>()
            .Select(pc => pc.Name.TextValue)
            .Distinct()
            .OrderBy(n => n)
            .ToArray();
    }

    // ========================= DRAW =========================
    public override void Draw()
    {
        // Top menu bar with buttons (Hunt / Murder Mystery / Bingo) + Settings to the right
        if (ImGui.BeginMenuBar())
        {
            if (ImGui.Button("Home")) _view = View.Home;
            ImGui.SameLine();
            if (ImGui.BeginMenu("Party"))
            {
                if (ImGui.MenuItem("Hunt")) _view = View.Hunt;
                if (ImGui.MenuItem("Murder Mystery")) _view = View.MurderMystery;
                if (ImGui.MenuItem("Glam Competition")) _view = View.Glam;
                if (ImGui.MenuItem("Spin Wheel")) _view = View.SpinWheel;
                ImGui.EndMenu();
            }
            ImGui.SameLine();
            if (ImGui.BeginMenu("Prizes"))
            {
                if (ImGui.MenuItem("Bingo"))
                {
                    _view = View.Bingo;
                    _ = Bingo_LoadGames();
                }
                if (ImGui.MenuItem("Raffle")) _view = View.Raffle;
                ImGui.EndMenu();
            }

            // push to right
            float rightEdge = ImGui.GetWindowContentRegionMax().X;
            float settingsW = 90f;
            ImGui.SameLine(0, 0);
            ImGui.SetCursorPosX(Math.Max(0, rightEdge - settingsW));
            if (ImGui.SmallButton("[Settings]"))
                Plugin.ToggleConfigUI();

            ImGui.EndMenuBar();
        }

        // left width slider
        float w = _leftPaneWidth;
        ImGui.SameLine();
        ImGui.SetNextItemWidth(200f);
        if (ImGui.SliderFloat("Left pane width", ref w, 240f, 600f))
            _leftPaneWidth = w;

        ImGui.Separator();

        // Two pane layout via Columns (API 13-safe)
        ImGui.Columns(2, "MainColumns", true);
        ImGui.SetColumnWidth(0, _leftPaneWidth);

        DrawLeftPane();

        ImGui.NextColumn();
        ImGui.BeginChild("RightPane", Vector2.Zero, false, 0);
        {
            switch (_view)
            {
                case View.Home: DrawHomePanel(); break;
                case View.Hunt: DrawHuntPanel(); break;
                case View.MurderMystery: DrawMurderMysteryPanel(); break;
                case View.Bingo: DrawBingoAdminPanel(); break;
                case View.Raffle: DrawRafflePanel(); break;
                case View.SpinWheel: DrawSpinWheelPanel(); break;
                case View.Glam: DrawGlamRoulettePanel(); break;
            }
        }
        ImGui.EndChild();

        ImGui.Columns(1);
    }

    // ========================= LEFT PANE =========================
    private void DrawLeftPane()
    {
        float totalH = ImGui.GetContentRegionAvail().Y;
        float topH = Math.Max(SplitterMinTop, totalH * _leftSplitRatio - SplitterThickness * 0.5f);
        float bottomH = Math.Max(SplitterMinBottom, totalH - topH - SplitterThickness);

        ImGui.BeginChild("PlayersTop", new Vector2(0, topH), true, 0);
        DrawPlayersList();
        ImGui.EndChild();

        // splitter
        ImGui.Button(" ", new Vector2(-1, SplitterThickness));
        if (ImGui.IsItemActive() && ImGui.IsMouseDragging(0))
        {
            float delta = ImGui.GetIO().MouseDelta.Y;
            float newTop = topH + delta;
            float newRatio = (newTop + SplitterThickness * 0.5f) / Math.Max(1f, totalH);
            float minRatio = SplitterMinTop / Math.Max(1f, totalH);
            float maxRatio = 1f - (SplitterMinBottom / Math.Max(1f, totalH));
            _leftSplitRatio = Math.Clamp(newRatio, minRatio, maxRatio);
        }

        ImGui.BeginChild("SavedBottom", new Vector2(0, bottomH), true, 0);
        if (_view == View.Bingo)
            DrawBingoGamesList();
        else if (_view == View.Raffle)
            DrawRaffleEntrantsList();
        else if (_view == View.SpinWheel)
            DrawSpinWheelPromptsList();
        else if (_view == View.Glam)
            DrawGlamContestantsList();
        else
            DrawSavedMurderGames();
        ImGui.EndChild();
    }

    // --- Player list: full-width hit area; right-click opens context ---
    private void DrawPlayersList()
    {
        ImGui.TextDisabled("Players (nearby)");
        ImGui.Separator();
        ImGui.Spacing();

        float rowH = ImGui.GetTextLineHeightWithSpacing();
        float padX = 6f;

        if (_nearbyPlayers.Length == 0)
        {
            ImGui.TextDisabled("No players nearby.");
            return;
        }

        foreach (var name in _nearbyPlayers)
        {
            string ownerKey = name; // live key is the name
            string display = ownerKey;

            var startPos = ImGui.GetCursorScreenPos();
            float fullW = ImGui.GetContentRegionAvail().X;
            ImGui.InvisibleButton($"##player-row-{ownerKey}", new Vector2(fullW, rowH));

            bool hovered = ImGui.IsItemHovered();
            bool leftClick = ImGui.IsItemClicked(Dalamud.Bindings.ImGui.ImGuiMouseButton.Left);
            bool rightClick = ImGui.IsItemClicked(Dalamud.Bindings.ImGui.ImGuiMouseButton.Right);
            bool isSelected = string.Equals(_selectedOwner, ownerKey, StringComparison.Ordinal);

            if (leftClick) _selectedOwner = ownerKey;
            if (rightClick) ImGui.OpenPopup($"ctx-player-{ownerKey}");

            // paint background
            var draw = ImGui.GetWindowDrawList();
            uint bg =
                isSelected ? ImGui.ColorConvertFloat4ToU32(new Vector4(0.30f, 0.30f, 0.45f, 0.55f)) :
                hovered ? ImGui.ColorConvertFloat4ToU32(new Vector4(0.30f, 0.30f, 0.30f, 0.35f)) :
                0;
            if (bg != 0)
                draw.AddRectFilled(startPos, new Vector2(startPos.X + fullW, startPos.Y + rowH), bg);

            // colorize text by MM status (like old window)
            var game = Plugin.Config.CurrentGame;
            bool isActive = game?.ActivePlayers.Contains(ownerKey) ?? false;
            bool isDead = game?.DeadPlayers.Contains(ownerKey) ?? false;
            bool isImprisoned = game?.ImprisonedPlayers.Contains(ownerKey) ?? false;

            Vector4 textColor = new(1, 1, 1, 1);
            string suffix = "";
            if (isDead) { textColor = new Vector4(1.0f, 0.2f, 0.2f, 1.0f); suffix = " (Dead)"; }
            else if (isImprisoned) { textColor = new Vector4(0.2f, 0.2f, 1.0f, 1.0f); suffix = " (Imprisoned)"; }
            else if (isActive) { textColor = new Vector4(0.2f, 1.0f, 0.2f, 1.0f); suffix = " (Active)"; }

            var cur = ImGui.GetCursorScreenPos();
            ImGui.SetCursorScreenPos(new Vector2(startPos.X + padX, startPos.Y + (rowH - ImGui.GetTextLineHeight()) * 0.5f));
            using (var col = ImRaii.PushColor(Dalamud.Bindings.ImGui.ImGuiCol.Text, ImGui.ColorConvertFloat4ToU32(textColor)))
            {
                ImGui.TextUnformatted(display + suffix);
            }
            ImGui.SetCursorScreenPos(cur);

            if (hovered) ImGui.SetTooltip("Right-click for actions");

            // Context menu
            if (ImGui.BeginPopup($"ctx-player-{ownerKey}"))
            {
                // Murder Mystery submenu
                if (ImGui.BeginMenu("Murder Mystery"))
                {
                    if (game == null)
                    {
                        ImGui.MenuItem("(no current game)", false, false);
                    }
                    else
                    {
                        game.ActivePlayers ??= new List<string>();
                        game.DeadPlayers ??= new List<string>();
                        game.ImprisonedPlayers ??= new List<string>();

                        bool isA = game.ActivePlayers.Contains(ownerKey);
                        bool isD = game.DeadPlayers.Contains(ownerKey);
                        bool isI = game.ImprisonedPlayers.Contains(ownerKey);

                        if (ImGui.MenuItem(isA ? "Remove from Active" : "Add to Active"))
                        {
                            if (isA) game.ActivePlayers.RemoveAll(p => p == ownerKey);
                            else if (!game.ActivePlayers.Contains(ownerKey)) game.ActivePlayers.Add(ownerKey);
                            Plugin.Config.Save();
                            _view = View.MurderMystery;
                            _selectedOwner = ownerKey;
                        }
                        if (ImGui.MenuItem(isD ? "Unmark Dead" : "Mark Dead"))
                        {
                            if (isD) game.DeadPlayers.RemoveAll(p => p == ownerKey);
                            else
                            {
                                if (!game.DeadPlayers.Contains(ownerKey)) game.DeadPlayers.Add(ownerKey);
                                game.ImprisonedPlayers.RemoveAll(p => p == ownerKey);
                            }
                            Plugin.Config.Save();
                            _view = View.MurderMystery;
                            _selectedOwner = ownerKey;
                        }
                        if (ImGui.MenuItem(isI ? "Unmark Imprisoned" : "Mark Imprisoned"))
                        {
                            if (isI) game.ImprisonedPlayers.RemoveAll(p => p == ownerKey);
                            else
                            {
                                if (!game.ImprisonedPlayers.Contains(ownerKey)) game.ImprisonedPlayers.Add(ownerKey);
                                game.DeadPlayers.RemoveAll(p => p == ownerKey);
                            }
                            Plugin.Config.Save();
                            _view = View.MurderMystery;
                            _selectedOwner = ownerKey;
                        }
                    }
                    ImGui.EndMenu();
                }

                // Bingo submenu
                if (ImGui.BeginMenu("Bingo"))
                {
                    if (ImGui.MenuItem("View Cards"))
                    {
                        _selectedOwner = ownerKey;
                        _ = Bingo_LoadOwnerCardsForOwner(ownerKey);
                        _view = View.Bingo;
                    }
                    if (ImGui.MenuItem("Buy 1 Card"))
                    {
                        _selectedOwner = ownerKey;
                        _ = Bingo_BuyForOwner(ownerKey, 1);
                        _view = View.Bingo;
                    }
                    if (ImGui.MenuItem("Buy 10 Cards"))
                    {
                        _selectedOwner = ownerKey;
                        _ = Bingo_BuyForOwner(ownerKey, 10);
                        _view = View.Bingo;
                    }
                    ImGui.EndMenu();
                }

                // Raffle submenu
                if (ImGui.BeginMenu("Raffle"))
                {
                    if (ImGui.MenuItem("Add to Raffle"))
                    {
                        _view = View.Raffle;
                        Raffle_AddEntry(ownerKey, "manual");
                    }
                    ImGui.EndMenu();
                }

                // Glam Roulette submenu
                if (ImGui.BeginMenu("Glam Roulette"))
                {
                    if (ImGui.MenuItem("Add contestant"))
                    {
                        _view = View.Glam;
                        Glam_AddContestant(ownerKey);
                    }
                    ImGui.EndMenu();
                }

                // Hunt placeholder
                if (ImGui.BeginMenu("Hunt"))
                {
                    ImGui.MenuItem("(no actions yet)", false, false);
                    ImGui.EndMenu();
                }

                ImGui.EndPopup();
            }
        }
    }

    // -------- bottom-left when Murder tab is active --------
    private void DrawSavedMurderGames()
    {
        ImGui.TextDisabled("Murder Mystery Games");
        ImGui.Separator();
        ImGui.Spacing();

        // + and - like old window
        if (ImGui.Button("+"))
        {
            var newGame = new MurderMysteryData { Title = $"New Game {Plugin.Config.MurderMysteryGames.Count + 1}" };
            Plugin.Config.MurderMysteryGames.Add(newGame);
            Plugin.Config.CurrentGame = newGame;
            Plugin.Config.Save();
        }
        ImGui.SameLine();
        bool canDel = Plugin.Config.CurrentGame != null;
        using (var dis = ImRaii.Disabled(!canDel))
        {
            if (ImGui.Button("-") && canDel)
            {
                var current = Plugin.Config.CurrentGame!;
                Plugin.Config.MurderMysteryGames.Remove(current);
                Plugin.Config.CurrentGame = Plugin.Config.MurderMysteryGames.FirstOrDefault();
                Plugin.Config.Save();
            }
        }

        ImGui.Spacing();

        // list of games
        for (int i = 0; i < Plugin.Config.MurderMysteryGames.Count; i++)
        {
            var g = Plugin.Config.MurderMysteryGames[i];
            bool isCurrent = Plugin.Config.CurrentGame == g;
            string title = string.IsNullOrEmpty(g.Title) ? $"Game {i + 1}" : g.Title;

            // highlight current (yellow like old)
            if (isCurrent)
            {
                using var col = ImRaii.PushColor(Dalamud.Bindings.ImGui.ImGuiCol.Text,
                    ImGui.ColorConvertFloat4ToU32(new Vector4(1.0f, 1.0f, 0.0f, 1.0f)));
                if (ImGui.Selectable(title, isCurrent))
                {
                    Plugin.Config.CurrentGame = g;
                    Plugin.Config.Save();
                    _view = View.MurderMystery;
                }
            }
            else
            {
                if (ImGui.Selectable(title, isCurrent))
                {
                    Plugin.Config.CurrentGame = g;
                    Plugin.Config.Save();
                    _view = View.MurderMystery;
                }
            }
        }
    }

    // -------- bottom-left when Bingo tab is active --------
    // -------- bottom-left when Bingo tab is active --------
    private void DrawBingoGamesList()
    {
        ImGui.TextDisabled("Bingo Games");
        ImGui.SameLine();
        if (ImGui.SmallButton("Refresh"))
            _ = Bingo_LoadGames();

        if (_bingoGamesLoading)
        {
            ImGui.SameLine();
            ImGui.TextDisabled("Loading…");
        }

        ImGui.Separator();
        ImGui.Spacing();

        if (_bingoGames.Count == 0)
        {
            ImGui.TextDisabled("No games found. Click Refresh.");
            return;
        }

        foreach (var g in _bingoGames)
        {
            var id = g.game_id ?? string.Empty;
            var title = string.IsNullOrWhiteSpace(g.title) ? id : g.title;
            var created = (g.created_at.HasValue && g.created_at.Value > 0)
                ? DateTimeOffset.FromUnixTimeSeconds((long)g.created_at.Value).ToLocalTime().ToString("yyyy-MM-dd HH:mm")
                : "unknown";
            var status = g.active ? "active" : "ended";

            bool isLoaded = string.Equals(_bingoState?.game.game_id, id, StringComparison.Ordinal)
                            || string.Equals(_bingoGameId, id, StringComparison.Ordinal);

            if (ImGui.Selectable($"{title}##{id}", isLoaded))
            {
                _bingoGameId = id;
                _ = Bingo_LoadGame(_bingoGameId);
            }

            ImGui.SameLine();
            ImGui.TextDisabled($"[{status}] {created}  stage:{g.stage}  pot:{g.pot}");
        }
    }


    // ========================= RIGHT PANES =========================
        private void DrawHomePanel()
    {
                var iconSize = new Vector2(28, 28);
        if (_homeIconTexture != null)
        {
            var wrap = _homeIconTexture.GetWrapOrDefault();
            ImGui.Image(wrap.Handle, iconSize);
        }
        else
        {
            ImGui.ColorButton("##home_icon", new Vector4(0.35f, 0.75f, 0.55f, 1f), 0, iconSize);
        }
        ImGui.SameLine();
        ImGui.TextUnformatted("Forest Home");
        ImGui.Separator();
        ImGui.TextWrapped("Forest is a lightweight admin console for TheBigTree games.");
        ImGui.Spacing();
        ImGui.TextUnformatted("What you can do:");
        ImGui.BulletText("Manage Bingo games, players, and claims.");
        ImGui.BulletText("Run Murder Mystery sessions.");
        ImGui.BulletText("Track nearby players for quick actions.");
        ImGui.Spacing();
        ImGui.TextDisabled("Use the tabs above to jump into a mode.");
    }
private void DrawHuntPanel()
    {
        ImGui.TextUnformatted("Hunt panel (placeholder).");
    }

    private void DrawMurderMysteryPanel()
    {
        var game = Plugin.Config.CurrentGame;

        if (game == null)
        {
            ImGui.TextDisabled("No murder mystery game selected. Create or select one on the left.");
            return;
        }
        NormalizeMurderMysteryData(game);

        ImGui.TextDisabled("Murder Mystery Details");
        ImGui.Separator();
        ImGui.Spacing();

        // Title
        string title = game.Title ?? "";
        if (ImGui.InputText("Title", ref title, 256))
        {
            game.Title = title;
            Plugin.Config.Save();
        }

        // Description
        ImGui.Text("Description:");
        string desc = game.Description ?? "";
        var descSize = new Vector2(ImGui.GetContentRegionAvail().X, 80);
        if (ImGui.InputTextMultiline("##description", ref desc, 2048, descSize, 0))
        {
            game.Description = desc;
            Plugin.Config.Save();
        }

        ImGui.Spacing();
        ImGui.Separator();
        ImGui.Text("Voting Period:");

        if (_votingStartTime.HasValue)
        {
            var remaining = _votingDuration - (DateTime.UtcNow - _votingStartTime.Value);
            if (remaining.TotalSeconds > 0)
            {
                ImGui.TextColored(new Vector4(1.0f, 0.8f, 0.0f, 1.0f), $"Voting active: {remaining:mm\\:ss} remaining");
                ImGui.SameLine();
                if (ImGui.Button("Stop Voting"))
                {
                    ProcessVotingResults();
                    _votingStartTime = null;
                    Plugin.Config.Save();
                }

                if (_receivedWhispers.Count > 0)
                {
                    ImGui.Text("Received Whispers:");
                    ImGui.Indent();
                    foreach (var kv in _receivedWhispers)
                        ImGui.TextColored(new Vector4(0.8f, 1.0f, 0.8f, 1.0f), $"{kv.Key}: {kv.Value}");
                    ImGui.Unindent();
                }
            }
            else
            {
                ImGui.TextColored(new Vector4(1.0f, 0.2f, 0.2f, 1.0f), "Voting period ended");
                ImGui.SameLine();
                if (ImGui.Button("Reset"))
                {
                    ProcessVotingResults();
                    _votingStartTime = null;
                    Plugin.Config.Save();
                }
            }
        }
        else
        {
            if (ImGui.Button("Start 5-Minute Voting"))
                StartVotingPeriod();
        }

        ImGui.Spacing();
        ImGui.Separator();
        ImGui.Text("Active Players (click to set as killer):");
        ImGui.Indent();

        // Click to set killer, remove buttons like old
        for (int i = game.ActivePlayers.Count - 1; i >= 0; i--)
        {
            string playerName = game.ActivePlayers[i];
            bool isKiller = game.Killer == playerName;
            bool isDead = game.DeadPlayers.Contains(playerName);
            bool isImprisoned = game.ImprisonedPlayers.Contains(playerName);

            Vector4 color = new(1, 1, 1, 1);
            if (isDead) color = new Vector4(1.0f, 0.2f, 0.2f, 1.0f);
            else if (isImprisoned) color = new Vector4(0.2f, 0.2f, 1.0f, 1.0f);
            else if (isKiller) color = new Vector4(1.0f, 0.2f, 0.2f, 1.0f);

            string display = $"• {playerName}" +
                (isDead ? " (Dead)" :
                 isImprisoned ? " (Imprisoned)" :
                 isKiller ? " (Killer)" : "");

            using (var c = ImRaii.PushColor(Dalamud.Bindings.ImGui.ImGuiCol.Text, ImGui.ColorConvertFloat4ToU32(color)))
            {
                if (ImGui.Selectable(display, isKiller))
                {
                    game.Killer = playerName;
                    Plugin.Config.Save();
                }
            }

            ImGui.SameLine();
            ImGui.PushID(i);
            if (ImGui.SmallButton("Remove"))
            {
                game.ActivePlayers.RemoveAt(i);
                game.DeadPlayers.Remove(playerName);
                game.ImprisonedPlayers.Remove(playerName);
                if (game.Killer == playerName) game.Killer = "";
                Plugin.Config.Save();
            }
            ImGui.PopID();
        }
        ImGui.Unindent();

        if (game.ActivePlayers.Count == 0)
            ImGui.TextDisabled("No active players. Right-click a player (left list) to add.");

        ImGui.Spacing();

        // Whisper requirements like old code
        int reqWhispers = GetRequiredWhisperFields();
        int totalRoundsMM = reqWhispers + 1;
        int livingPlayers = game.ActivePlayers.Count
            - game.DeadPlayers.Count
            - game.ImprisonedPlayers.Count
            - (string.IsNullOrEmpty(game.Killer) ? 0 : 1);

        ImGui.Text($"Required Whisper Fields: {reqWhispers}");
        ImGui.Text($"Total Rounds: {totalRoundsMM}");
        ImGui.Text($"Living Players: {Math.Max(0, livingPlayers)}");

        ImGui.Spacing();

        // Killer + Prize
        string killer = game.Killer ?? "";
        if (ImGui.InputText("Killer", ref killer, 256))
        {
            game.Killer = killer;
            Plugin.Config.Save();
        }

        string prize = game.Prize ?? "";
        if (ImGui.InputText("Prize", ref prize, 256))
        {
            game.Prize = prize;
            Plugin.Config.Save();
        }

        ImGui.Spacing();
        ImGui.Separator();
        ImGui.Text("Hint Timers (mm:ss):");

        // Dynamic timers: exactly as old logic
        int totalRounds = reqWhispers + 1;
        for (int i = 0; i < totalRounds; i++)
        {
            DrawCountdownHint($"Hint {i + 1} Timer", game, i);
        }
    }
    private void DrawBingoAdminPanel()
    {
        // ====== Admin UI status ======
        bool connected = Plugin.Config.BingoConnected;
        if (connected)
            ImGui.TextColored(new Vector4(0.5f, 1f, 0.6f, 1f), "Connected");
        else
            ImGui.TextColored(new Vector4(1f, 0.55f, 0.55f, 1f), "Not connected");

        ImGui.SameLine();
        if (ImGui.SmallButton("Settings"))
            Plugin.ToggleConfigUI();

        if (!string.IsNullOrEmpty(Plugin.Config.BingoServerInfo))
        {
            ImGui.SameLine();
            ImGui.TextDisabled($"[{Plugin.Config.BingoServerInfo}]");
        }
        if (!string.IsNullOrEmpty(_bingoStatus))
        {
            ImGui.SameLine();
            ImGui.TextDisabled(_bingoStatus);
        }
        if (_bingoLoading)
        {
            ImGui.SameLine();
            ImGui.TextDisabled("Loading.");
        }

        ImGui.Separator();

        if (!connected)
        {
            ImGui.TextDisabled("Set your Auth Token in Settings to connect.");
            return;
        }

        if (_bingoShowBuyLink)
        {
            ImGui.OpenPopup("Player link");
            _bingoShowBuyLink = false;
        }
        var showLinkModal = true;
        if (ImGui.BeginPopupModal("Player link", ref showLinkModal, ImGuiWindowFlags.AlwaysAutoResize))
        {
            ImGui.TextUnformatted($"Player: {_bingoBuyOwner}");
            ImGui.SetNextItemWidth(420);
            ImGui.InputText("Link", ref _bingoBuyLink, 1024, ImGuiInputTextFlags.ReadOnly);
            if (ImGui.Button("Copy link"))
                ImGui.SetClipboardText(_bingoBuyLink);
            ImGui.SameLine();
            if (ImGui.Button("Close"))
                showLinkModal = false;
            ImGui.EndPopup();
        }

        // ====== Game Id + controls ======
        ImGui.Text("Game Id:");
        ImGui.SameLine();
        ImGui.SetNextItemWidth(260);
        ImGui.InputText("##bingo_game", ref _bingoGameId, 128);
        ImGui.SameLine();

        bool hasGame = _bingoState is not null;
        if (ImGui.Button("Load Game")) _ = Bingo_LoadGame(_bingoGameId);
        ImGui.SameLine();
        using (var dis = ImRaii.Disabled(!hasGame))
        {
            if (ImGui.Button("Start")) _ = Bingo_Start();
            ImGui.SameLine();
            if (ImGui.Button("End")) _ = Bingo_End();
            ImGui.SameLine();
            if (ImGui.Button("Roll")) _ = Bingo_Roll();
            ImGui.SameLine();
            if (ImGui.Button("Advance Stage")) _ = Bingo_AdvanceStage();
        }

        ImGui.Spacing();

        if (_bingoState is null)
        {
            ImGui.TextDisabled("Select a game from the list on the left.");
            return;
        }

        var g = _bingoState.game;
        ImGui.TextUnformatted($"Game: {g.title} ({g.game_id})");
        ImGui.SameLine(); ImGui.TextDisabled($"Stage: {g.stage}");
        ImGui.Spacing();
        ImGui.TextUnformatted($"Pot: {g.pot} {g.currency}");
        ImGui.SameLine();
        ImGui.TextDisabled($"Payouts S:{g.payouts.single} D:{g.payouts.@double} F:{g.payouts.full}");
        ImGui.Separator();

        ImGui.TextUnformatted("Called:");
        ImGui.SameLine();
        int? lastCalled = g.last_called;
        if ((!lastCalled.HasValue || lastCalled.Value == 0) && g.called is { Length: > 0 })
            lastCalled = g.called[^1];
        ImGui.SetNextItemWidth(120);
        ImGui.BeginChild("LastDrawBox", new Vector2(120, 64), true, ImGuiWindowFlags.NoScrollbar);
        ImGui.TextDisabled("Last draw");
        ImGui.SetWindowFontScale(2.2f);
        ImGui.TextUnformatted(lastCalled.HasValue ? lastCalled.Value.ToString() : "--");
        ImGui.SetWindowFontScale(1f);
        ImGui.EndChild();
        foreach (var r in g.called ?? Array.Empty<int>())
        {
            ImGui.SameLine();
            ImGui.TextColored(new Vector4(0.5f, 1f, 0.6f, 1f), r.ToString());
        }
        ImGui.Spacing();
        ImGui.BeginChild("ClaimsRow", new Vector2(0, 72), false, ImGuiWindowFlags.NoScrollbar);
        ImGui.BeginChild("LastDrawBoxRow", new Vector2(120, 64), true, ImGuiWindowFlags.NoScrollbar);
        ImGui.TextDisabled("Last draw");
        ImGui.SetWindowFontScale(2.2f);
        ImGui.TextUnformatted(lastCalled.HasValue ? lastCalled.Value.ToString() : "--");
        ImGui.SetWindowFontScale(1f);
        ImGui.EndChild();
        ImGui.SameLine();
        ImGui.BeginChild("ClaimsBox", new Vector2(0, 64), true, ImGuiWindowFlags.NoScrollbar);
        ImGui.TextDisabled("Claims");
        var claims = g.claims ?? Array.Empty<Claim>();
        if (claims.Length == 0)
        {
            ImGui.TextDisabled("No claims.");
        }
        else
        {
            foreach (var c in claims)
            {
                var status = c.pending ? "pending" : (c.denied ? "denied" : "approved");
                ImGui.TextUnformatted($"{c.owner_name} - {c.card_id} - {c.stage} - {status}");
                if (c.pending)
                {
                    ImGui.SameLine();
                    if (ImGui.SmallButton($"Approve##{c.card_id}"))
                        _ = Bingo_ApproveClaim(c.card_id);
                    ImGui.SameLine();
                    if (ImGui.SmallButton($"Deny##{c.card_id}"))
                        _ = Bingo_DenyClaim(c.card_id);
                }
            }
        }
        ImGui.EndChild();
        ImGui.EndChild();
        ImGui.Separator();

        ImGui.TextUnformatted("Owners:");
        if (_bingoOwners.Count > 0)
        {
            foreach (var owner in _bingoOwners)
            {
                ImGui.SameLine();
                if (ImGui.Button($"{owner.owner_name} ({owner.cards})"))
                    _ = Bingo_LoadOwnerCards(owner.owner_name);
            }
        }
        else
        {
            ImGui.SameLine();
            ImGui.SetNextItemWidth(200);
            ImGui.InputText("Owner", ref _bingoManualOwner, 128);
            ImGui.SameLine();
            if (ImGui.Button("Fetch Cards") && !string.IsNullOrWhiteSpace(_bingoManualOwner))
                _ = Bingo_LoadOwnerCards(_bingoManualOwner);
        }

        ImGui.Spacing();

        foreach (var kv in _bingoOwnerCards)
        {
            if (ImGui.CollapsingHeader($"{kv.Key}##owner-{kv.Key}", ImGuiTreeNodeFlags.DefaultOpen))
            {
                foreach (var card in kv.Value)
                {
                    Bingo_DrawCard(card, g.called ?? Array.Empty<int>());
                    ImGui.Separator();
                }
            }
        }
    }

    // ========================= Murder Mystery helpers =========================
    private int GetRequiredWhisperFields()
    {
        var game = Plugin.Config.CurrentGame;
        if (game == null) return 0;
        return GetRequiredWhisperFields(game);
    }

    // ========================= Raffle =========================
    private void DrawRafflePanel()
    {
        var raffle = Plugin.Config.Raffle;

        ImGui.TextUnformatted("Forest Raffle Roll");
        ImGui.Separator();
        ImGui.Spacing();

        ImGui.SetNextItemWidth(300);
        string title = raffle.Title ?? "";
        if (ImGui.InputText("Title", ref title, 128))
        {
            raffle.Title = title;
            Plugin.Config.Save();
        }

        ImGui.SetNextItemWidth(420);
        string desc = raffle.Description ?? "";
        if (ImGui.InputText("Description", ref desc, 256))
        {
            raffle.Description = desc;
            Plugin.Config.Save();
        }

        ImGui.SetNextItemWidth(120);
        string join = raffle.JoinPhrase ?? "";
        if (ImGui.InputText("Join phrase", ref join, 64))
        {
            raffle.JoinPhrase = join;
            Plugin.Config.Save();
        }

        int minutes = Math.Clamp(raffle.SignupMinutes, 1, 30);
        if (ImGui.SliderInt("Signup minutes", ref minutes, 1, 30))
        {
            raffle.SignupMinutes = minutes;
            Plugin.Config.Save();
        }

        int winners = Math.Clamp(raffle.WinnersCount, 1, 10);
        if (ImGui.SliderInt("Winners", ref winners, 1, 10))
        {
            raffle.WinnersCount = winners;
            Plugin.Config.Save();
        }

        ImGui.TextUnformatted("Signup channels:");
        ImGui.SameLine();
        bool say = raffle.AllowSay;
        if (ImGui.Checkbox("Say", ref say)) { raffle.AllowSay = say; Plugin.Config.Save(); }
        ImGui.SameLine();
        bool shout = raffle.AllowShout;
        if (ImGui.Checkbox("Shout", ref shout)) { raffle.AllowShout = shout; Plugin.Config.Save(); }
        ImGui.SameLine();
        bool yell = raffle.AllowYell;
        if (ImGui.Checkbox("Yell", ref yell)) { raffle.AllowYell = yell; Plugin.Config.Save(); }
        ImGui.SameLine();
        bool party = raffle.AllowParty;
        if (ImGui.Checkbox("Party", ref party)) { raffle.AllowParty = party; Plugin.Config.Save(); }
        ImGui.SameLine();
        bool tell = raffle.AllowTell;
        if (ImGui.Checkbox("Tell", ref tell)) { raffle.AllowTell = tell; Plugin.Config.Save(); }

        bool autoDraw = raffle.AutoDrawOnClose;
        if (ImGui.Checkbox("Auto-draw on close", ref autoDraw))
        {
            raffle.AutoDrawOnClose = autoDraw;
            Plugin.Config.Save();
        }

        ImGui.SetNextItemWidth(240);
        string salt = raffle.HostSalt ?? "";
        if (ImGui.InputText("Seed salt", ref salt, 128))
        {
            raffle.HostSalt = salt;
            Plugin.Config.Save();
        }

        ImGui.SetNextItemWidth(420);
        string webhook = raffle.WebhookUrl ?? "";
        if (ImGui.InputText("Discord webhook", ref webhook, 512))
        {
            raffle.WebhookUrl = webhook;
            Plugin.Config.Save();
        }

        ImGui.Spacing();

        if (!string.IsNullOrWhiteSpace(_raffleStatus))
            ImGui.TextDisabled(_raffleStatus);

        ImGui.Spacing();

        using (var dis = ImRaii.Disabled(raffle.IsOpen))
        {
            if (ImGui.Button("Start Raffle"))
                Raffle_Start();
        }
        ImGui.SameLine();
        using (var dis = ImRaii.Disabled(!raffle.IsOpen))
        {
            if (ImGui.Button("Close Raffle"))
                Raffle_Close();
        }
        ImGui.SameLine();
        if (ImGui.Button("Draw"))
            Raffle_Draw();

        ImGui.Spacing();
        ImGui.Separator();

        ImGui.TextUnformatted($"Entrants: {raffle.Entries.Count}");
        if (raffle.IsOpen && raffle.EndsAtUtc.HasValue)
        {
            var remaining = raffle.EndsAtUtc.Value - DateTime.UtcNow;
            if (remaining.TotalSeconds > 0)
                ImGui.TextDisabled($"Closes in: {remaining:mm\\:ss}");
        }

        if (raffle.Winners.Count > 0)
        {
            ImGui.Spacing();
            ImGui.TextUnformatted("Winners:");
            foreach (var w in raffle.Winners)
                ImGui.BulletText($"{w.Name} (#{w.TicketNumber})");
        }
    }

    // ========================= Spin Wheel =========================
    private void DrawSpinWheelPanel()
    {
        var wheel = Plugin.Config.SpinWheel;
        EnsureWheelDefaults(wheel);

        ImGui.TextUnformatted("Spin the Wheel");
        ImGui.Separator();
        ImGui.Spacing();

        ImGui.SetNextItemWidth(300);
        string title = wheel.Title ?? "";
        if (ImGui.InputText("Title", ref title, 128))
        {
            wheel.Title = title;
            Plugin.Config.Save();
        }

        ImGui.SetNextItemWidth(420);
        string template = wheel.AnnouncementTemplate ?? "";
        if (ImGui.InputText("Announcement", ref template, 256))
        {
            wheel.AnnouncementTemplate = template;
            Plugin.Config.Save();
        }

        ImGui.SetNextItemWidth(420);
        string punishTemplate = wheel.PunishmentTemplate ?? "";
        if (ImGui.InputText("Punishment announce", ref punishTemplate, 256))
        {
            wheel.PunishmentTemplate = punishTemplate;
            Plugin.Config.Save();
        }

        int cooldown = Math.Clamp(wheel.CooldownSpins, 0, 10);
        if (ImGui.SliderInt("Cooldown spins", ref cooldown, 0, 10))
        {
            wheel.CooldownSpins = cooldown;
            Plugin.Config.Save();
        }

        bool announce = wheel.AnnounceInChat;
        if (ImGui.Checkbox("Announce in chat", ref announce))
        {
            wheel.AnnounceInChat = announce;
            Plugin.Config.Save();
        }
        ImGui.SameLine();
        bool usePunish = wheel.UsePunishments;
        if (ImGui.Checkbox("Use punishments", ref usePunish))
        {
            wheel.UsePunishments = usePunish;
            Plugin.Config.Save();
        }
        ImGui.SameLine();
        bool punishLoserOnly = wheel.PunishLoserOnly;
        if (ImGui.Checkbox("Punish loser only", ref punishLoserOnly))
        {
            wheel.PunishLoserOnly = punishLoserOnly;
            Plugin.Config.Save();
        }

        ImGui.Spacing();
        if (!string.IsNullOrWhiteSpace(_wheelStatus))
            ImGui.TextDisabled(_wheelStatus);

        if (ImGui.Button("Spin"))
            SpinWheel();

        ImGui.SameLine();
        using (var dis = ImRaii.Disabled(!wheel.UsePunishments))
        {
            if (ImGui.Button("Spin punishment"))
                SpinWheelPunishment();
        }

        ImGui.SameLine();
        if (ImGui.Button("Reset History"))
        {
            foreach (var p in wheel.Prompts)
                p.LastUsedSpin = -1;
            foreach (var p in wheel.PunishmentPrompts)
                p.LastUsedSpin = -1;
            wheel.SpinCount = 0;
            wheel.LastPrompt = "";
            Plugin.Config.Save();
            _wheelStatus = "History reset.";
        }

        ImGui.Spacing();
        ImGui.Separator();

        ImGui.BeginChild("WheelLastPrompt", new Vector2(220, 84), true);
        ImGui.TextDisabled("Last prompt");
        ImGui.SetWindowFontScale(1.8f);
        ImGui.TextWrapped(string.IsNullOrWhiteSpace(wheel.LastPrompt) ? "--" : wheel.LastPrompt);
        ImGui.SetWindowFontScale(1f);
        ImGui.EndChild();
    }

    // ========================= Glam Roulette =========================
    private void DrawGlamRoulettePanel()
    {
        var glam = Plugin.Config.GlamRoulette;
        EnsureGlamDefaults(glam);

        ImGui.TextUnformatted("Glam Roulette");
        ImGui.Separator();
        ImGui.Spacing();

        ImGui.SetNextItemWidth(300);
        string title = glam.Title ?? "";
        if (ImGui.InputText("Title", ref title, 128))
        {
            glam.Title = title;
            Plugin.Config.Save();
        }

        ImGui.SetNextItemWidth(120);
        string voteKeyword = glam.VoteKeyword ?? "";
        if (ImGui.InputText("Vote keyword", ref voteKeyword, 64))
        {
            glam.VoteKeyword = voteKeyword;
            Plugin.Config.Save();
        }

        int minutes = Math.Clamp(glam.RoundMinutes, 2, 5);
        if (ImGui.SliderInt("Round minutes", ref minutes, 2, 5))
        {
            glam.RoundMinutes = minutes;
            Plugin.Config.Save();
        }

        ImGui.TextUnformatted("Vote channels:");
        ImGui.SameLine();
        bool say = glam.AllowSay;
        if (ImGui.Checkbox("Say", ref say)) { glam.AllowSay = say; Plugin.Config.Save(); }
        ImGui.SameLine();
        bool shout = glam.AllowShout;
        if (ImGui.Checkbox("Shout", ref shout)) { glam.AllowShout = shout; Plugin.Config.Save(); }
        ImGui.SameLine();
        bool yell = glam.AllowYell;
        if (ImGui.Checkbox("Yell", ref yell)) { glam.AllowYell = yell; Plugin.Config.Save(); }
        ImGui.SameLine();
        bool party = glam.AllowParty;
        if (ImGui.Checkbox("Party", ref party)) { glam.AllowParty = party; Plugin.Config.Save(); }
        ImGui.SameLine();
        bool tell = glam.AllowTell;
        if (ImGui.Checkbox("Tell", ref tell)) { glam.AllowTell = tell; Plugin.Config.Save(); }

        ImGui.Spacing();
        if (!string.IsNullOrWhiteSpace(_glamStatus))
            ImGui.TextDisabled(_glamStatus);

        ImGui.Spacing();

        if (ImGui.Button("Roll Theme"))
            Glam_RollTheme();
        ImGui.SameLine();
        if (ImGui.Button("Start Round"))
            Glam_StartRound();
        ImGui.SameLine();
        if (ImGui.Button("End Round"))
            Glam_EndRound();
        ImGui.SameLine();
        if (ImGui.Button("Toggle Voting"))
            Glam_ToggleVoting();

        ImGui.Spacing();
        ImGui.Separator();

        ImGui.BeginChild("GlamThemeBox", new Vector2(240, 84), true);
        ImGui.TextDisabled("Current theme");
        ImGui.SetWindowFontScale(1.8f);
        ImGui.TextWrapped(string.IsNullOrWhiteSpace(glam.CurrentTheme) ? "--" : glam.CurrentTheme);
        ImGui.SetWindowFontScale(1f);
        ImGui.EndChild();

        if (glam.RoundActive && glam.EndsAtUtc.HasValue)
        {
            var remaining = glam.EndsAtUtc.Value - DateTime.UtcNow;
            if (remaining.TotalSeconds > 0)
                ImGui.TextDisabled($"Time left: {remaining:mm\\:ss}");
        }

        ImGui.Spacing();
        ImGui.Separator();

        ImGui.TextUnformatted("Vote tally:");
        foreach (var kv in Glam_GetVoteCounts(glam))
        {
            ImGui.BulletText($"{kv.Key}: {kv.Value}");
        }
    }

    private void DrawGlamContestantsList()
    {
        var glam = Plugin.Config.GlamRoulette;
        EnsureGlamDefaults(glam);

        ImGui.TextDisabled("Glam Contestants");
        ImGui.SameLine();
        ImGui.TextDisabled($"[{glam.Contestants.Count}]");
        ImGui.Separator();
        ImGui.Spacing();

        for (int i = 0; i < glam.Contestants.Count; i++)
        {
            var c = glam.Contestants[i];
            ImGui.TextUnformatted($"{i + 1}. {c.Name}");
            ImGui.SameLine();
            ImGui.PushID(i);
            if (ImGui.SmallButton("Remove"))
            {
                glam.Contestants.RemoveAt(i);
                Plugin.Config.Save();
            }
            ImGui.PopID();
        }

        ImGui.Spacing();
        if (ImGui.Button("Add contestant"))
        {
            glam.Contestants.Add(new GlamContestant { Name = "New contestant", Order = glam.Contestants.Count + 1 });
            Plugin.Config.Save();
        }
    }

    private void EnsureGlamDefaults(GlamRouletteState glam)
    {
        if (glam.Themes.Count > 0) return;

        if (TryLoadGlamDefaults(out var themes))
        {
            if (themes.Count > 0)
            {
                glam.Themes = themes.Select(t => new GlamTheme { Text = t }).ToList();
                Plugin.Config.Save();
                return;
            }
        }

        glam.Themes = new List<GlamTheme>
        {
            new() { Text = "Skater Prince" },
            new() { Text = "Forest Bandit Boy" },
            new() { Text = "Sadboy in Pastel" },
            new() { Text = "Gridania but make it trashy" },
            new() { Text = "Starry Night Idol" },
            new() { Text = "Battle-worn Librarian" },
            new() { Text = "High Society Rebel" },
            new() { Text = "Crimson Duelist" },
            new() { Text = "Rainy Day Tourist" },
            new() { Text = "Woodland Mage" },
        };
        Plugin.Config.Save();
    }

    private void Glam_AddContestant(string name)
    {
        var glam = Plugin.Config.GlamRoulette;
        var trimmed = (name ?? "").Trim();
        if (string.IsNullOrEmpty(trimmed)) return;
        if (glam.Contestants.Any(c => string.Equals(c.Name, trimmed, StringComparison.OrdinalIgnoreCase)))
            return;
        glam.Contestants.Add(new GlamContestant { Name = trimmed, Order = glam.Contestants.Count + 1 });
        Plugin.Config.Save();
    }

    private void Glam_RollTheme()
    {
        var glam = Plugin.Config.GlamRoulette;
        EnsureGlamDefaults(glam);
        if (glam.Themes.Count == 0)
        {
            _glamStatus = "No themes available.";
            return;
        }
        int idx = RandomNumberGenerator.GetInt32(0, glam.Themes.Count);
        glam.CurrentTheme = glam.Themes[idx].Text;
        _glamStatus = $"Theme: {glam.CurrentTheme}";
        Plugin.Config.Save();
    }

    private void Glam_StartRound()
    {
        var glam = Plugin.Config.GlamRoulette;
        if (string.IsNullOrWhiteSpace(glam.CurrentTheme))
            Glam_RollTheme();
        glam.RoundActive = true;
        glam.StartedAtUtc = DateTime.UtcNow;
        glam.EndsAtUtc = DateTime.UtcNow.AddMinutes(Math.Clamp(glam.RoundMinutes, 2, 5));
        glam.VotesByVoter.Clear();
        _glamStatus = "Round started.";
        Plugin.Config.Save();
    }

    private void Glam_EndRound()
    {
        var glam = Plugin.Config.GlamRoulette;
        glam.RoundActive = false;
        glam.VotingOpen = false;
        glam.EndsAtUtc = DateTime.UtcNow;
        _glamStatus = "Round ended.";
        Plugin.Config.Save();
    }

    private void Glam_ToggleVoting()
    {
        var glam = Plugin.Config.GlamRoulette;
        glam.VotingOpen = !glam.VotingOpen;
        _glamStatus = glam.VotingOpen ? "Voting opened." : "Voting closed.";
        Plugin.Config.Save();
    }

    private bool Glam_HandleVote(XivChatType type, string sender, string message)
    {
        var glam = Plugin.Config.GlamRoulette;
        if (!glam.RoundActive || !glam.VotingOpen) return false;
        if (string.IsNullOrWhiteSpace(glam.VoteKeyword)) return false;

        bool channelOk = type switch
        {
            XivChatType.Say => glam.AllowSay,
            XivChatType.Shout => glam.AllowShout,
            XivChatType.Yell => glam.AllowYell,
            XivChatType.Party => glam.AllowParty,
            XivChatType.TellIncoming => glam.AllowTell,
            _ => false
        };
        if (!channelOk) return false;

        int idx = message.IndexOf(glam.VoteKeyword, StringComparison.OrdinalIgnoreCase);
        if (idx < 0) return false;

        var after = message.Substring(idx + glam.VoteKeyword.Length).Trim();
        if (string.IsNullOrWhiteSpace(after)) return false;

        var match = glam.Contestants.FirstOrDefault(c =>
            string.Equals(c.Name, after, StringComparison.OrdinalIgnoreCase));
        if (match == null) return false;

        glam.VotesByVoter[sender] = match.Name;
        Plugin.Config.Save();
        return true;
    }

    private Dictionary<string, int> Glam_GetVoteCounts(GlamRouletteState glam)
    {
        var counts = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
        foreach (var c in glam.Contestants)
            counts[c.Name] = 0;
        foreach (var kv in glam.VotesByVoter)
        {
            if (!counts.ContainsKey(kv.Value))
                counts[kv.Value] = 0;
            counts[kv.Value] += 1;
        }
        return counts;
    }

    private void DrawSpinWheelPromptsList()
    {
        var wheel = Plugin.Config.SpinWheel;
        EnsureWheelDefaults(wheel);

        ImGui.TextDisabled("Wheel Prompts");
        ImGui.SameLine();
        ImGui.TextDisabled($"[{wheel.Prompts.Count}]");
        ImGui.Separator();
        ImGui.Spacing();

        for (int i = 0; i < wheel.Prompts.Count; i++)
        {
            var prompt = wheel.Prompts[i];
            ImGui.PushID(i);

            ImGui.SetNextItemWidth(200);
            string text = prompt.Text ?? "";
            if (ImGui.InputText("##prompt", ref text, 256))
            {
                prompt.Text = text;
                Plugin.Config.Save();
            }

            ImGui.SameLine();
            ImGui.SetNextItemWidth(60);
            int weight = Math.Clamp(prompt.Weight, 1, 10);
            if (ImGui.InputInt("##weight", ref weight))
            {
                prompt.Weight = Math.Clamp(weight, 1, 10);
                Plugin.Config.Save();
            }
            ImGui.SameLine();
            ImGui.TextDisabled("w");

            ImGui.SameLine();
            if (ImGui.SmallButton("Remove"))
            {
                wheel.Prompts.RemoveAt(i);
                Plugin.Config.Save();
            }

            ImGui.PopID();
        }

        ImGui.Spacing();
        if (ImGui.Button("Add prompt"))
        {
            wheel.Prompts.Add(new WheelPrompt { Text = "New prompt", Weight = 1 });
            Plugin.Config.Save();
        }

        ImGui.Spacing();
        ImGui.Separator();
        ImGui.TextDisabled("Punishment Prompts");
        ImGui.SameLine();
        ImGui.TextDisabled($"[{wheel.PunishmentPrompts.Count}]");
        ImGui.Spacing();

        for (int i = 0; i < wheel.PunishmentPrompts.Count; i++)
        {
            var prompt = wheel.PunishmentPrompts[i];
            ImGui.PushID(i + 10000);

            ImGui.SetNextItemWidth(200);
            string text = prompt.Text ?? "";
            if (ImGui.InputText("##punish", ref text, 256))
            {
                prompt.Text = text;
                Plugin.Config.Save();
            }

            ImGui.SameLine();
            ImGui.SetNextItemWidth(60);
            int weight = Math.Clamp(prompt.Weight, 1, 10);
            if (ImGui.InputInt("##punishweight", ref weight))
            {
                prompt.Weight = Math.Clamp(weight, 1, 10);
                Plugin.Config.Save();
            }
            ImGui.SameLine();
            ImGui.TextDisabled("w");

            ImGui.SameLine();
            if (ImGui.SmallButton("Remove"))
            {
                wheel.PunishmentPrompts.RemoveAt(i);
                Plugin.Config.Save();
            }

            ImGui.PopID();
        }

        ImGui.Spacing();
        if (ImGui.Button("Add punishment"))
        {
            wheel.PunishmentPrompts.Add(new WheelPrompt { Text = "New punishment", Weight = 1 });
            Plugin.Config.Save();
        }
    }

    private void EnsureWheelDefaults(SpinWheelState wheel)
    {
        if (wheel.Prompts.Count > 0) return;

        if (TryLoadSpinWheelDefaults(out var prompts, out var punishments))
        {
            if (prompts.Count > 0)
                wheel.Prompts = prompts.Select(p => new WheelPrompt { Text = p, Weight = 1 }).ToList();
            if (punishments.Count > 0)
                wheel.PunishmentPrompts = punishments.Select(p => new WheelPrompt { Text = p, Weight = 1 }).ToList();
            Plugin.Config.Save();
            return;
        }

        wheel.Prompts = new List<WheelPrompt>
        {
            new() { Text = "Do your favorite emote.", Weight = 2 },
            new() { Text = "Strike a dramatic pose and hold for 5 seconds.", Weight = 2 },
            new() { Text = "Use a /shout with a goofy catchphrase.", Weight = 1 },
            new() { Text = "Pick a random player and compliment their glam.", Weight = 2 },
            new() { Text = "Change minion to something tiny.", Weight = 1 },
            new() { Text = "Do a quick 5-second RP line.", Weight = 2 },
            new() { Text = "Spin in place three times.", Weight = 2 },
            new() { Text = "Swap to your silliest title.", Weight = 1 },
            new() { Text = "Use /laugh at the host.", Weight = 1 },
            new() { Text = "Do a victory emote for the crowd.", Weight = 2 },
            new() { Text = "Make a bad pun about trees.", Weight = 1 },
            new() { Text = "Pick a new standing pose.", Weight = 1 },
        };
        wheel.PunishmentPrompts = new List<WheelPrompt>
        {
            new() { Text = "Do a full /grovel to the crowd.", Weight = 2 },
            new() { Text = "Sing one line of a song in /say.", Weight = 2 },
            new() { Text = "Do 10 seconds of dramatic crying emotes.", Weight = 2 },
            new() { Text = "Change to the silliest weapon glam you own.", Weight = 1 },
            new() { Text = "Use /slap on the host (politely).", Weight = 1 },
            new() { Text = "Do a slow walk to the center and bow.", Weight = 2 },
        };
        Plugin.Config.Save();
    }

    private sealed class SpinWheelDefaults
    {
        public List<string>? prompts { get; set; }
        public List<string>? punishments { get; set; }
    }

    private sealed class GlamDefaults
    {
        public List<string>? themes { get; set; }
    }

    private bool TryLoadSpinWheelDefaults(out List<string> prompts, out List<string> punishments)
    {
        prompts = new List<string>();
        punishments = new List<string>();

        if (!TryReadDefaultsJson("spin-wheel.json", out var json))
            return false;

        try
        {
            var data = JsonSerializer.Deserialize<SpinWheelDefaults>(json);
            if (data?.prompts != null) prompts = data.prompts.Where(p => !string.IsNullOrWhiteSpace(p)).ToList();
            if (data?.punishments != null) punishments = data.punishments.Where(p => !string.IsNullOrWhiteSpace(p)).ToList();
            return prompts.Count > 0 || punishments.Count > 0;
        }
        catch
        {
            return false;
        }
    }

    private bool TryLoadGlamDefaults(out List<string> themes)
    {
        themes = new List<string>();
        if (!TryReadDefaultsJson("glam-roulette.json", out var json))
            return false;

        try
        {
            var data = JsonSerializer.Deserialize<GlamDefaults>(json);
            if (data?.themes != null)
                themes = data.themes.Where(t => !string.IsNullOrWhiteSpace(t)).ToList();
            return themes.Count > 0;
        }
        catch
        {
            return false;
        }
    }

    private bool TryReadDefaultsJson(string fileName, out string json)
    {
        json = "";
        var baseDir = Forest.Plugin.PluginInterface.AssemblyLocation.DirectoryName ?? "";
        var current = new DirectoryInfo(baseDir);
        for (int i = 0; i < 6 && current != null; i++)
        {
            var path = Path.Combine(current.FullName, "defaults", fileName);
            if (File.Exists(path))
            {
                json = File.ReadAllText(path);
                return true;
            }
            current = current.Parent;
        }
        return false;
    }

    private void SpinWheel()
    {
        var wheel = Plugin.Config.SpinWheel;
        EnsureWheelDefaults(wheel);

        if (wheel.Prompts.Count == 0)
        {
            _wheelStatus = "No prompts available.";
            return;
        }

        var picked = SpinWheelPick(wheel.Prompts, wheel);
        if (picked == null) return;

        wheel.LastPrompt = picked.Text;
        _wheelStatus = $"Spin #{wheel.SpinCount}: {picked.Text}";
        Plugin.Config.Save();

        if (wheel.AnnounceInChat)
        {
            var msg = (wheel.AnnouncementTemplate ?? "[Wheel] {prompt}")
                .Replace("{prompt}", picked.Text);
            Plugin.ChatGui.Print(msg);
        }
    }

    private void SpinWheelPunishment()
    {
        var wheel = Plugin.Config.SpinWheel;
        EnsureWheelDefaults(wheel);
        if (wheel.PunishmentPrompts.Count == 0)
        {
            _wheelStatus = "No punishment prompts available.";
            return;
        }

        var picked = SpinWheelPick(wheel.PunishmentPrompts, wheel);
        if (picked == null) return;

        _wheelStatus = $"Punishment #{wheel.SpinCount}: {picked.Text}";
        Plugin.Config.Save();

        if (wheel.AnnounceInChat)
        {
            var msg = (wheel.PunishmentTemplate ?? "[Wheel][Punishment] {prompt}")
                .Replace("{prompt}", picked.Text);
            Plugin.ChatGui.Print(msg);
        }
    }

    private WheelPrompt? SpinWheelPick(List<WheelPrompt> prompts, SpinWheelState wheel)
    {
        var eligible = new List<WheelPrompt>();
        foreach (var p in prompts)
        {
            if (wheel.CooldownSpins <= 0 || p.LastUsedSpin < 0 ||
                (wheel.SpinCount - p.LastUsedSpin) > wheel.CooldownSpins)
            {
                if (!string.IsNullOrWhiteSpace(p.Text))
                    eligible.Add(p);
            }
        }
        if (eligible.Count == 0)
        {
            _wheelStatus = "All prompts are on cooldown.";
            return null;
        }

        int totalWeight = 0;
        foreach (var p in eligible) totalWeight += Math.Max(1, p.Weight);
        int roll = RandomNumberGenerator.GetInt32(0, totalWeight);
        WheelPrompt? picked = null;
        int acc = 0;
        foreach (var p in eligible)
        {
            acc += Math.Max(1, p.Weight);
            if (roll < acc) { picked = p; break; }
        }
        if (picked == null) return null;

        wheel.SpinCount += 1;
        picked.LastUsedSpin = wheel.SpinCount;
        return picked;
    }

    private void DrawRaffleEntrantsList()
    {
        var raffle = Plugin.Config.Raffle;
        ImGui.TextDisabled("Raffle Entrants");
        ImGui.SameLine();
        ImGui.TextDisabled($"[{raffle.Entries.Count}]");
        ImGui.Separator();
        ImGui.Spacing();

        if (raffle.Entries.Count == 0)
        {
            ImGui.TextDisabled("No entrants yet.");
            return;
        }

        for (int i = raffle.Entries.Count - 1; i >= 0; i--)
        {
            var entry = raffle.Entries[i];
            ImGui.TextUnformatted($"#{entry.TicketNumber} {entry.Name}");
            ImGui.SameLine();
            ImGui.PushID(i);
            if (ImGui.SmallButton("Remove"))
            {
                raffle.Entries.RemoveAt(i);
                Plugin.Config.Save();
            }
            ImGui.PopID();
        }
    }

    private void Raffle_Start()
    {
        var raffle = Plugin.Config.Raffle;
        raffle.IsOpen = true;
        raffle.StartedAtUtc = DateTime.UtcNow;
        raffle.EndsAtUtc = DateTime.UtcNow.AddMinutes(Math.Clamp(raffle.SignupMinutes, 1, 30));
        raffle.Entries.Clear();
        raffle.Winners.Clear();
        raffle.SeedHash = null;
        raffle.SeedSource = null;
        raffle.RandomBytes = null;
        _raffleStatus = "Raffle started.";
        Plugin.Config.Save();
    }

    private void Raffle_Close()
    {
        var raffle = Plugin.Config.Raffle;
        raffle.IsOpen = false;
        raffle.EndsAtUtc = DateTime.UtcNow;
        _raffleStatus = "Raffle closed.";
        Plugin.Config.Save();

        if (raffle.AutoDrawOnClose)
            Raffle_Draw();
    }

    private void Raffle_Draw()
    {
        var raffle = Plugin.Config.Raffle;
        if (raffle.Entries.Count == 0)
        {
            _raffleStatus = "No entrants to draw.";
            return;
        }

        int winnersToPick = Math.Clamp(raffle.WinnersCount, 1, 10);
        if (!raffle.AllowRepeatWinners && winnersToPick > raffle.Entries.Count)
            winnersToPick = raffle.Entries.Count;

        var seedSource = Raffle_BuildSeedSource(raffle);
        var seedHash = Raffle_HashSeed(seedSource);
        raffle.SeedSource = seedSource;
        raffle.SeedHash = seedHash;

        var rng = Raffle_CreateRng(seedHash);
        var pool = new List<RaffleEntry>(raffle.Entries);
        raffle.Winners.Clear();

        for (int i = 0; i < winnersToPick; i++)
        {
            if (pool.Count == 0) break;
            int idx = rng.Next(pool.Count);
            var pick = pool[idx];
            raffle.Winners.Add(new RaffleWinner { Name = pick.Name, TicketNumber = pick.TicketNumber });
            if (!raffle.AllowRepeatWinners)
                pool.RemoveAt(idx);
        }

        _raffleStatus = $"Draw complete ({raffle.Winners.Count} winners).";
        Plugin.Config.Save();

        Plugin.ChatGui.Print($"[Raffle] Winners: {string.Join(", ", raffle.Winners.Select(w => w.Name))}");
        _ = Raffle_PostWebhook(raffle);
    }

    private string Raffle_BuildSeedSource(RaffleState raffle)
    {
        if (string.IsNullOrWhiteSpace(raffle.RandomBytes))
        {
            var bytes = RandomNumberGenerator.GetBytes(8);
            raffle.RandomBytes = Convert.ToBase64String(bytes);
        }
        long roundedTime = raffle.StartedAtUtc.HasValue
            ? (long)raffle.StartedAtUtc.Value.ToUniversalTime().Subtract(DateTime.UnixEpoch).TotalSeconds
            : (long)DateTime.UtcNow.Subtract(DateTime.UnixEpoch).TotalSeconds;
        return $"{raffle.HostSalt}|{roundedTime}|{raffle.Entries.Count}|{raffle.RandomBytes}";
    }

    private static string Raffle_HashSeed(string seedSource)
    {
        var bytes = SHA256.HashData(Encoding.UTF8.GetBytes(seedSource));
        var sb = new StringBuilder(bytes.Length * 2);
        foreach (var b in bytes) sb.Append(b.ToString("x2"));
        return sb.ToString();
    }

    private static Random Raffle_CreateRng(string seedHash)
    {
        int seed = 0;
        if (!string.IsNullOrWhiteSpace(seedHash) && seedHash.Length >= 8)
            seed = Convert.ToInt32(seedHash.Substring(0, 8), 16);
        return new Random(seed);
    }

    private void Raffle_AddEntry(string name, string source)
    {
        var raffle = Plugin.Config.Raffle;
        if (!raffle.IsOpen)
        {
            _raffleStatus = "Raffle is not open.";
            return;
        }
        var trimmed = (name ?? "").Trim();
        if (string.IsNullOrEmpty(trimmed)) return;

        if (!raffle.AllowAlts)
        {
            if (raffle.Entries.Any(e => string.Equals(e.Name, trimmed, StringComparison.OrdinalIgnoreCase)))
                return;
        }

        int ticket = raffle.Entries.Count + 1;
        raffle.Entries.Add(new RaffleEntry
        {
            Name = trimmed,
            TicketNumber = ticket,
            Source = source ?? ""
        });
        _raffleStatus = $"{trimmed} entered.";
        Plugin.Config.Save();
    }

    private bool Raffle_HandleChatJoin(XivChatType type, string sender, string message)
    {
        var raffle = Plugin.Config.Raffle;
        if (!raffle.IsOpen) return false;
        if (string.IsNullOrWhiteSpace(raffle.JoinPhrase)) return false;

        bool channelOk = type switch
        {
            XivChatType.Say => raffle.AllowSay,
            XivChatType.Shout => raffle.AllowShout,
            XivChatType.Yell => raffle.AllowYell,
            XivChatType.Party => raffle.AllowParty,
            XivChatType.TellIncoming => raffle.AllowTell,
            _ => false
        };
        if (!channelOk) return false;

        if (message.IndexOf(raffle.JoinPhrase, StringComparison.OrdinalIgnoreCase) < 0)
            return false;

        Raffle_AddEntry(sender, "chat");
        return true;
    }

    private void Raffle_CheckAutoClose()
    {
        var raffle = Plugin.Config.Raffle;
        if (!raffle.IsOpen || !raffle.EndsAtUtc.HasValue) return;
        if (DateTime.UtcNow < raffle.EndsAtUtc.Value) return;

        raffle.IsOpen = false;
        raffle.EndsAtUtc = DateTime.UtcNow;
        _raffleStatus = "Raffle closed.";
        Plugin.Config.Save();

        if (raffle.AutoDrawOnClose)
            Raffle_Draw();
    }

    private async Task Raffle_PostWebhook(RaffleState raffle)
    {
        if (string.IsNullOrWhiteSpace(raffle.WebhookUrl)) return;

        try
        {
            using var http = new HttpClient();
            var winners = raffle.Winners.Count == 0
                ? "No winners."
                : string.Join("\n", raffle.Winners.Select(w => $"{w.Name} (#{w.TicketNumber})"));
            var payload = new
            {
                username = "Forest Raffle",
                embeds = new[]
                {
                    new
                    {
                        title = raffle.Title,
                        description = raffle.Description,
                        fields = new[]
                        {
                            new { name = "Entrants", value = raffle.Entries.Count.ToString(), inline = true },
                            new { name = "Winners", value = winners, inline = false },
                            new { name = "Seed", value = raffle.SeedHash ?? "n/a", inline = false },
                        }
                    }
                }
            };
            var json = System.Text.Json.JsonSerializer.Serialize(payload);
            using var content = new StringContent(json, Encoding.UTF8, "application/json");
            await http.PostAsync(raffle.WebhookUrl, content).ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            _raffleStatus = $"Webhook failed: {ex.Message}";
        }
    }

    private int GetRequiredWhisperFields(MurderMysteryData game)
    {
        int active = game.ActivePlayers.Count;
        if (active == 0) return 0;

        int killer = string.IsNullOrEmpty(game.Killer) ? 0 : 1;
        int living = active - killer - game.DeadPlayers.Count - game.ImprisonedPlayers.Count;
        return living > 0 ? Math.Max(1, living / 2) : 0;
    }

    private void StartVotingPeriod()
    {
        _votingStartTime = DateTime.UtcNow;
        _receivedWhispers.Clear();
        _whispersProcessed.Clear();
        Plugin.ChatGui.Print("[Murder Mystery] Voting period started! Send your votes via whisper.");
        Plugin.Config.Save();
    }

    private void ProcessVotingResults()
    {
        var game = Plugin.Config.CurrentGame;
        if (game == null || _receivedWhispers.Count == 0) return;

        foreach (var kv in _receivedWhispers)
        {
            string playerName = kv.Key;
            string whisperText = kv.Value;

            if (!Plugin.Config.PlayerDatabase.TryGetValue(playerName, out var pdata))
            {
                pdata = new PlayerData { Name = playerName };
                Plugin.Config.PlayerDatabase[playerName] = pdata;
            }

            // first empty slot
            int slot = 0;
            while (!string.IsNullOrEmpty(pdata.GetWhisper(slot))) slot++;
            pdata.SetWhisper(slot, whisperText);
        }

        Plugin.ChatGui.Print($"[Murder Mystery] Processed {_receivedWhispers.Count} whispers from voting period.");
        _receivedWhispers.Clear();
    }

    private void DrawCountdownHint(string label, MurderMysteryData game, int idx)
    {
        var time = game.GetHintTime(idx);
        var text = game.GetHintText(idx);
        var endTime = game.GetTimerEndTime(idx);
        var notified = game.GetTimerNotified(idx);

        ImGui.Text(label);
        ImGui.Indent();

        ImGui.SetNextItemWidth(120);
        string timeStr = time ?? "";
        if (ImGui.InputText($"Time##{label}", ref timeStr, 32))
        {
            game.SetHintTime(idx, timeStr);
            Plugin.Config.Save();
        }

        ImGui.SameLine();

        bool isRunning = endTime > DateTime.UtcNow;
        if (isRunning)
        {
            if (ImGui.Button($"Stop##{label}"))
            {
                game.SetTimerEndTime(idx, DateTime.MinValue);
                Plugin.Config.Save();
            }

            ImGui.SameLine();
            var remaining = endTime - DateTime.UtcNow;
            if (remaining.TotalSeconds > 0)
                ImGui.Text($"({remaining.Minutes:D2}:{remaining.Seconds:D2})");
            else
                ImGui.TextColored(new Vector4(1.0f, 0.0f, 0.0f, 1.0f), "(FINISHED)");
        }
        else
        {
            if (ImGui.Button($"Start##{label}"))
            {
                if (ParseTimeString(timeStr, out int min, out int sec))
                {
                    var newEnd = DateTime.UtcNow.AddMinutes(min).AddSeconds(sec);
                    game.SetTimerEndTime(idx, newEnd);
                    game.SetTimerNotified(idx, false);
                    Plugin.Config.Save();
                }
            }
        }

        string textStr = text ?? "";
        var hintSize = new Vector2(ImGui.GetContentRegionAvail().X, 60);
        if (ImGui.InputTextMultiline($"##{label}Text", ref textStr, 1024, hintSize))
        {
            game.SetHintText(idx, textStr);
            Plugin.Config.Save();
        }

        ImGui.Unindent();
        ImGui.Spacing();
    }

    private bool ParseTimeString(string s, out int minutes, out int seconds)
    {
        minutes = 0; seconds = 0;
        if (string.IsNullOrWhiteSpace(s)) return false;
        var parts = s.Split(':');
        if (parts.Length == 2) return int.TryParse(parts[0], out minutes) && int.TryParse(parts[1], out seconds);
        if (parts.Length == 1) return int.TryParse(parts[0], out minutes);
        return false;
    }

    private void CheckVotingPeriod()
    {
        if (!_votingStartTime.HasValue) return;

        if (DateTime.UtcNow - _votingStartTime.Value >= _votingDuration)
        {
            Plugin.ChatGui.Print("[Murder Mystery] Voting period has ended!");
            ProcessVotingResults();
            _votingStartTime = null;
            Plugin.Config.Save();
        }
    }

    private void CheckCountdownCompletion()
    {
        var game = Plugin.Config.CurrentGame;
        if (game == null) return;

        var now = DateTime.UtcNow;
        foreach (var kv in game.TimerEndTimes.ToList())
        {
            int idx = kv.Key;
            DateTime end = kv.Value;
            bool notified = game.GetTimerNotified(idx);
            string text = game.GetHintText(idx);

            if (!notified && end != DateTime.MinValue && now >= end)
            {
                Plugin.ChatGui.Print($"[Murder Mystery] Hint {idx + 1} : {text}");
                game.SetTimerNotified(idx, true);
                Plugin.Config.Save();
            }
        }
    }

    // ========================= Bingo helpers =========================
    private void Bingo_DrawCard(CardInfo card, int[] called)
    {
        var numbers = card.numbers ?? Array.Empty<int[]>();
        int n = Math.Max(1, numbers.Length);
        ImGui.TextDisabled($"Card {card.card_id} - {n}x{n}");

        bool isWin = Bingo_CheckCardWin(card, called);
        if (isWin)
        {
            ImGui.SameLine();
            ImGui.TextColored(new Vector4(1f, 0.85f, 0.3f, 1f), "BINGO!");
        }

        float avail = ImGui.GetContentRegionAvail().X;
        float cell = Math.Max(26f, Math.Min(58f, avail / (n + 0.5f)));
        var calledSet = new HashSet<int>(called ?? Array.Empty<int>());

        for (int r = 0; r < numbers.Length; r++)
        {
            var row = numbers[r];
            for (int c = 0; c < row.Length; c++)
            {
                int val = row[c];
                bool marked = false;
                if (card.marks != null && r < card.marks.Length && c < card.marks[r].Length)
                    marked = card.marks[r][c];
                if (!marked && calledSet.Contains(val))
                    marked = true;

                Vector4 color = marked ? new Vector4(0.20f, 0.38f, 0.85f, 1f)
                                      : new Vector4(0.25f, 0.25f, 0.25f, 1f);
                using (var btnCol = ImRaii.PushColor(Dalamud.Bindings.ImGui.ImGuiCol.Button, ImGui.ColorConvertFloat4ToU32(color)))
                    ImGui.Button(val.ToString(), new Vector2(cell, cell));

                if (c < row.Length - 1) ImGui.SameLine();
            }
        }
    }

    private static bool Bingo_CheckCardWin(CardInfo card, int[] called)
    {
        var nums = card.numbers ?? Array.Empty<int[]>();
        if (nums.Length == 0) return false;
        var marks = card.marks ?? Array.Empty<bool[]>();
        var calledSet = new HashSet<int>(called ?? Array.Empty<int>());
        int n = nums.Length;

        bool IsMarked(int r, int c)
        {
            if (r < marks.Length && c < marks[r].Length && marks[r][c]) return true;
            if (r < nums.Length && c < nums[r].Length && calledSet.Contains(nums[r][c])) return true;
            return false;
        }

        for (int r = 0; r < n; r++)
        {
            bool row = true;
            for (int c = 0; c < n; c++) row &= IsMarked(r, c);
            if (row) return true;
        }
        for (int c = 0; c < n; c++)
        {
            bool col = true;
            for (int r = 0; r < n; r++) col &= IsMarked(r, c);
            if (col) return true;
        }
        bool diag = true;
        for (int i = 0; i < n; i++) diag &= IsMarked(i, i);
        if (diag) return true;
        bool diag2 = true;
        for (int i = 0; i < n; i++) diag2 &= IsMarked(i, n - 1 - i);
        return diag2;
    }

    private void Bingo_EnsureClient()
    {
        if (_bingoApi is not null) return;

        // pulls both values from config
        _bingoApi = new BingoAdminApiClient(
            Plugin.Config.BingoApiBaseUrl ?? "https://server.thebigtree.life:8443",
            Plugin.Config.BingoApiKey
        );
    }


    private async Task Bingo_LoadGame(string gameId)
    {
        if (string.IsNullOrWhiteSpace(gameId)) { _bingoStatus = "Game ID required."; return; }
        Bingo_EnsureClient();
        _bingoLoading = true; _bingoStatus = "Loading game.";
        _bingoCts?.Cancel(); _bingoCts = new CancellationTokenSource();

        try
        {
            _bingoState = await _bingoApi!.GetStateAsync(gameId, _bingoCts.Token);
            _bingoOwnerCards.Clear();
            _bingoOwners = new List<OwnerSummary>();
            _bingoGameId = _bingoState.game.game_id;
            _bingoStatus = $"Loaded '{_bingoState.game.title}'.";
            await Bingo_LoadOwners();
        }
        catch (Exception ex) { _bingoStatus = $"Failed: {ex.Message}"; }
        finally { _bingoLoading = false; }
    }

    private async Task Bingo_LoadOwnerCards(string owner)
    {
        if (_bingoState is null) return;
        Bingo_EnsureClient();
        _bingoLoading = true; _bingoStatus = $"Loading cards for {owner}.";
        _bingoCts?.Cancel(); _bingoCts = new CancellationTokenSource();

        try
        {
            var response = await _bingoApi!.GetOwnerCardsAsync(_bingoState.game.game_id, owner, _bingoCts.Token);
            var cards = response.cards?.ToList() ?? new List<CardInfo>();
            _bingoOwnerCards[owner] = cards;
            _bingoState = new GameStateEnvelope(_bingoState.active, response.game, _bingoState.stats);
            _bingoStatus = $"Loaded {cards.Count} cards for {owner}.";
        }
        catch (Exception ex) { _bingoStatus = $"Failed: {ex.Message}"; }
        finally { _bingoLoading = false; }
    }

    private async Task Bingo_LoadOwners()
    {
        if (_bingoState is null) return;
        Bingo_EnsureClient();
        _bingoLoading = true; _bingoStatus = "Loading owners.";
        _bingoCts?.Cancel(); _bingoCts = new CancellationTokenSource();

        try
        {
            var response = await _bingoApi!.GetOwnersAsync(_bingoState.game.game_id, _bingoCts.Token);
            _bingoOwners = response.owners?.ToList() ?? new List<OwnerSummary>();
            _bingoStatus = $"Loaded {_bingoOwners.Count} owner(s).";
        }
        catch (Exception ex) { _bingoStatus = $"Failed: {ex.Message}"; }
        finally { _bingoLoading = false; }
    }

    private async Task Bingo_Start()
    {
        if (_bingoState is null)
        {
            _bingoStatus = "Load a game first.";
            return;
        }
        Bingo_EnsureClient();
        _bingoLoading = true; _bingoStatus = "Starting game.";

        try
        {
            await _bingoApi!.StartGameAsync(_bingoState.game.game_id);
            await Bingo_LoadGame(_bingoState.game.game_id);
            _bingoStatus = "Game started.";
        }
        catch (Exception ex) { _bingoStatus = $"Start failed: {ex.Message}"; }
        finally { _bingoLoading = false; }
    }

    private void NormalizeMurderMysteryData(MurderMysteryData game)
    {
        bool changed = false;
        var active = new List<string>();
        var dead = new List<string>();
        var imprisoned = new List<string>();

        var seenActive = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var name in game.ActivePlayers ?? new List<string>())
        {
            var trimmed = (name ?? "").Trim();
            if (string.IsNullOrEmpty(trimmed)) { changed = true; continue; }
            if (seenActive.Add(trimmed))
                active.Add(trimmed);
            else
                changed = true;
        }

        var seenDead = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var name in game.DeadPlayers ?? new List<string>())
        {
            var trimmed = (name ?? "").Trim();
            if (string.IsNullOrEmpty(trimmed)) { changed = true; continue; }
            if (seenDead.Add(trimmed))
                dead.Add(trimmed);
            else
                changed = true;
        }

        var seenImprisoned = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var name in game.ImprisonedPlayers ?? new List<string>())
        {
            var trimmed = (name ?? "").Trim();
            if (string.IsNullOrEmpty(trimmed)) { changed = true; continue; }
            if (seenImprisoned.Add(trimmed))
                imprisoned.Add(trimmed);
            else
                changed = true;
        }

        if (changed)
        {
            game.ActivePlayers = active;
            game.DeadPlayers = dead;
            game.ImprisonedPlayers = imprisoned;
        }

        int totalRounds = GetRequiredWhisperFields(game) + 1;
        changed |= PruneHintDict(game.HintTimes, totalRounds);
        changed |= PruneHintDict(game.HintTexts, totalRounds);
        changed |= PruneTimerDict(game.TimerEndTimes, totalRounds);
        changed |= PruneTimerDict(game.TimerNotified, totalRounds);

        if (changed)
            Plugin.Config.Save();
    }

    private static bool PruneHintDict(Dictionary<int, string> dict, int totalRounds)
    {
        if (dict.Count == 0) return false;
        bool changed = false;
        var remove = new List<int>();
        foreach (var key in dict.Keys)
        {
            if (key < 0 || key >= totalRounds)
                remove.Add(key);
        }
        foreach (var key in remove)
        {
            dict.Remove(key);
            changed = true;
        }
        return changed;
    }

    private static bool PruneTimerDict<T>(Dictionary<int, T> dict, int totalRounds)
    {
        if (dict.Count == 0) return false;
        bool changed = false;
        var remove = new List<int>();
        foreach (var key in dict.Keys)
        {
            if (key < 0 || key >= totalRounds)
                remove.Add(key);
        }
        foreach (var key in remove)
        {
            dict.Remove(key);
            changed = true;
        }
        return changed;
    }

    private async Task Bingo_End()
    {
        if (_bingoState is null)
        {
            _bingoStatus = "Load a game first.";
            return;
        }
        Bingo_EnsureClient();
        _bingoLoading = true; _bingoStatus = "Ending game.";

        try
        {
            await _bingoApi!.EndGameAsync(_bingoState.game.game_id);
            await Bingo_LoadGame(_bingoState.game.game_id);
            _bingoStatus = "Game ended.";
        }
        catch (Exception ex) { _bingoStatus = $"End failed: {ex.Message}"; }
        finally { _bingoLoading = false; }
    }

    private async Task Bingo_AdvanceStage()
    {
        if (_bingoState is null)
        {
            _bingoStatus = "Load a game first.";
            return;
        }
        Bingo_EnsureClient();
        _bingoLoading = true; _bingoStatus = "Advancing stage.";

        try
        {
            await _bingoApi!.AdvanceStageAsync(_bingoState.game.game_id);
            await Bingo_LoadGame(_bingoState.game.game_id);
            _bingoStatus = "Stage advanced.";
        }
        catch (Exception ex) { _bingoStatus = $"Advance failed: {ex.Message}"; }
        finally { _bingoLoading = false; }
    }

    private async Task Bingo_ApproveClaim(string cardId)
    {
        if (_bingoState is null)
        {
            _bingoStatus = "Load a game first.";
            return;
        }
        if (string.IsNullOrWhiteSpace(cardId))
        {
            _bingoStatus = "Card id required.";
            return;
        }
        Bingo_EnsureClient();
        _bingoLoading = true; _bingoStatus = "Approving claim.";

        try
        {
            await _bingoApi!.ApproveClaimAsync(_bingoState.game.game_id, cardId);
            await Bingo_LoadGame(_bingoState.game.game_id);
            _bingoStatus = "Claim approved.";
        }
        catch (Exception ex) { _bingoStatus = $"Approve failed: {ex.Message}"; }
        finally { _bingoLoading = false; }
    }

    private async Task Bingo_DenyClaim(string cardId)
    {
        if (_bingoState is null)
        {
            _bingoStatus = "Load a game first.";
            return;
        }
        if (string.IsNullOrWhiteSpace(cardId))
        {
            _bingoStatus = "Card id required.";
            return;
        }
        Bingo_EnsureClient();
        _bingoLoading = true; _bingoStatus = "Denying claim.";

        try
        {
            await _bingoApi!.DenyClaimAsync(_bingoState.game.game_id, cardId);
            await Bingo_LoadGame(_bingoState.game.game_id);
            _bingoStatus = "Claim denied.";
        }
        catch (Exception ex) { _bingoStatus = $"Deny failed: {ex.Message}"; }
        finally { _bingoLoading = false; }
    }

    private async Task Bingo_Roll()
    {
        if (_bingoState is null)
        {
            _bingoStatus = "Load a game first.";
            Plugin.ChatGui.PrintError("[Forest] Load a game first.");
            return;
        }
        Bingo_EnsureClient();
        _bingoRollAttempts = 0;
        _bingoLoading = true;
        _bingoStatus = "Rolling on server.";

        try
        {
            var previous = _bingoState.game.called ?? Array.Empty<int>();
            var prevSet = new HashSet<int>(previous);

            var res = await _bingoApi!.RollAsync(_bingoState.game.game_id);
            var called = res.called ?? previous;

            int? last = null;
            foreach (var num in called)
            {
                if (prevSet.Contains(num)) continue;
                if (!last.HasValue || num > last.Value)
                    last = num;
            }
            if (!last.HasValue && called.Length > 0)
                last = called[^1];

            _bingoState = _bingoState with { game = _bingoState.game with { called = called, last_called = last } };
            _bingoStatus = last.HasValue ? $"Rolled {last.Value}." : "Rolled.";
            if (last.HasValue)
                Plugin.ChatGui.Print($"[Forest] Called number {last.Value}.");
        }
        catch (Exception ex)
        {
            _bingoStatus = $"Failed: {ex.Message}";
            Plugin.ChatGui.PrintError($"[Forest] Roll failed: {ex.Message}");
        }
        finally
        {
            _bingoLoading = false;
        }
    }

    private bool TryHandleBingoRandom(string senderText, string messageText)
    {
        if (string.IsNullOrWhiteSpace(messageText)) return false;
        var lower = messageText.ToLowerInvariant();
        if (!lower.Contains("roll") && !lower.Contains("random") && !lower.Contains("lot")) return false;

        var localName = Plugin.ClientState.LocalPlayer?.Name.TextValue;
        var localLower = string.IsNullOrWhiteSpace(localName) ? "" : localName.ToLowerInvariant();
        var messageMatches =
            lower.Contains("you roll") ||
            lower.Contains("you rolled") ||
            lower.StartsWith("you ");
        if (!string.IsNullOrWhiteSpace(localLower))
        {
            var senderMatches = !string.IsNullOrWhiteSpace(senderText) &&
                                string.Equals(senderText, localName, StringComparison.OrdinalIgnoreCase);
            messageMatches = messageMatches || lower.Contains(localLower);
            if (!senderMatches && !messageMatches)
                return false;
        }
        var matches = Regex.Matches(messageText, "\\d+");
        if (matches.Count == 0) return false;
        if (!int.TryParse(matches[0].Value, out var rolled)) return false;
        _ = Bingo_HandleRandomResult(rolled);
        return true;
    }

    private async Task Bingo_HandleRandomResult(int rolled)
    {
        if (_bingoState is null)
        {
            _bingoStatus = "Load a game first.";
            Plugin.ChatGui.PrintError("[Forest] Load a game first.");
            return;
        }
        if (rolled < 1 || rolled > BingoRandomMax) return;

        var called = new HashSet<int>(_bingoState.game.called ?? Array.Empty<int>());
        if (called.Count >= BingoRandomMax)
        {
            _bingoStatus = "All numbers called.";
            Plugin.ChatGui.PrintError("[Forest] All numbers called.");
            return;
        }

        if (called.Contains(rolled))
        {
            _bingoRollAttempts += 1;
            if (_bingoRollAttempts > BingoRandomMax * 2)
            {
                _bingoStatus = "Too many repeats.";
                Plugin.ChatGui.PrintError("[Forest] Too many repeats while rolling.");
                return;
            }
            _bingoStatus = $"Number {rolled} already called.";
            Plugin.ChatGui.PrintError($"[Forest] Number {rolled} already called.");
            return;
        }

        try
        {
            var res = await _bingoApi!.CallNumberAsync(_bingoState.game.game_id, rolled);
            var newCalled = res.called ?? _bingoState.game.called ?? Array.Empty<int>();
            _bingoState = _bingoState with { game = _bingoState.game with { called = newCalled, last_called = rolled } };
            _bingoStatus = $"Rolled {rolled}.";
            Plugin.ChatGui.Print($"[Forest] Called number {rolled}.");
        }
        catch (Exception ex)
        {
            _bingoStatus = $"Failed: {ex.Message}";
            Plugin.ChatGui.PrintError($"[Forest] Call failed: {ex.Message}");
        }
    }
private Task Bingo_LoadOwnerCardsForOwner(string owner)
    {
        if (_bingoState is null)
        {
            _bingoStatus = "Load a game first.";
            return Task.CompletedTask;
        }
        return Bingo_LoadOwnerCards(owner);
    }

    private async Task Bingo_BuyForOwner(string owner, int count)
    {
        if (_bingoState is null)
        {
            _bingoStatus = "Load a game first.";
            return;
        }
        if (string.IsNullOrWhiteSpace(owner))
        {
            _bingoStatus = "Owner name required.";
            return;
        }
        Bingo_EnsureClient();
        _bingoLoading = true; _bingoStatus = $"Buying {count} card(s) for {owner}.";

        try
        {
            await _bingoApi!.BuyAsync(_bingoState.game.game_id, owner, count);
            await Bingo_LoadOwnerCards(owner);
            await Bingo_LoadOwners();
            _bingoStatus = $"Bought {count} for {owner}.";

            var ownerInfo = _bingoOwners.FirstOrDefault(o =>
                string.Equals(o.owner_name, owner, StringComparison.OrdinalIgnoreCase));
            if (!string.IsNullOrWhiteSpace(ownerInfo?.token))
            {
                var baseUrl = (Plugin.Config.BingoApiBaseUrl ?? "https://server.thebigtree.life:8443").TrimEnd('/');
                _bingoBuyLink = $"{baseUrl}/bingo/owner-token/{ownerInfo.token}";
                _bingoBuyOwner = ownerInfo.owner_name;
                _bingoShowBuyLink = true;
            }
            else
            {
                _bingoStatus = $"Bought {count} for {owner}, but no link token was found.";
            }
        }
        catch (Exception ex) { _bingoStatus = $"Buy failed: {ex.Message}"; }
        finally { _bingoLoading = false; }
    }
}
































