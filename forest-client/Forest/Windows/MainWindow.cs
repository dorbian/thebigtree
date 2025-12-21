using Dalamud.Bindings.ImGui; // API 13 ImGui bindings
using Dalamud.Game.ClientState;
using Dalamud.Game.ClientState.Objects;
using Dalamud.Game.ClientState.Objects.SubKinds;
using Dalamud.Game.Text;
using Dalamud.Game.Text.SeStringHandling;
using Dalamud.Interface.Utility.Raii;
using Dalamud.Interface.Windowing;
using Dalamud.Plugin.Services;

using Forest.Features.BingoAdmin;

using System;
using System.Collections.Generic;
using System.Linq;
using System.Numerics;
using System.Threading;
using System.Threading.Tasks;

using ImGuiWindowFlags = Dalamud.Bindings.ImGui.ImGuiWindowFlags;

namespace Forest.Windows;

public class MainWindow : Window, IDisposable
{
    private readonly Plugin Plugin;

    // ---------- View switch ----------
    private enum View { Hunt, MurderMystery, Bingo }
    private View _view = View.MurderMystery;

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

    public MainWindow(Plugin plugin)
        : base("Forest Manager##Main", ImGuiWindowFlags.NoScrollbar | ImGuiWindowFlags.NoScrollWithMouse | ImGuiWindowFlags.MenuBar)
    {
        Plugin = plugin;
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
            if (ImGui.Button("Hunt")) _view = View.Hunt;
            ImGui.SameLine();
            if (ImGui.Button("Murder Mystery")) _view = View.MurderMystery;
            ImGui.SameLine();
            if (ImGui.Button("Bingo")) _view = View.Bingo;

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
                case View.Hunt: DrawHuntPanel(); break;
                case View.MurderMystery: DrawMurderMysteryPanel(); break;
                case View.Bingo: DrawBingoAdminPanel(); break;
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
            DrawBingoGamesList();     // <— when Bingo tab is active
        else
            DrawSavedMurderGames();   // <— when Murder tab is active
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

        ImGui.Separator();

        if (!connected)
        {
            ImGui.TextDisabled("Set your Auth Token in Settings to connect.");
            return;
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
            if (ImGui.Button("Roll")) _ = Bingo_Roll();
            ImGui.SameLine();
            if (ImGui.Button("Advance Stage")) _ = Bingo_AdvanceStage();
        }

        if (!string.IsNullOrEmpty(_bingoStatus))
        {
            ImGui.SameLine(); ImGui.TextDisabled(_bingoStatus);
        }
        if (_bingoLoading)
        {
            ImGui.SameLine(); ImGui.TextDisabled("Loading.");
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
        foreach (var r in g.called ?? Array.Empty<int>())
        {
            ImGui.SameLine();
            ImGui.TextColored(new Vector4(0.5f, 1f, 0.6f, 1f), r.ToString());
        }
        ImGui.Separator();

        ImGui.TextUnformatted("Claims:");
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

    private async Task Bingo_Roll()
    {
        if (_bingoState is null) return;
        Bingo_EnsureClient();
        _bingoLoading = true; _bingoStatus = "Rolling.";
        try
        {
            var res = await _bingoApi!.RollAsync(_bingoState.game.game_id);
            var called = res.called ?? Array.Empty<int>();
            _bingoState = _bingoState with { game = _bingoState.game with { called = called } };
            _bingoStatus = called.Length > 0 ? $"Rolled {called[^1]}." : "Rolled.";
        }
        catch (Exception ex) { _bingoStatus = $"Failed: {ex.Message}"; }
        finally { _bingoLoading = false; }
    }

        private async Task Bingo_Start()
    {
        if (_bingoState is null) return;
        Bingo_EnsureClient();
        _bingoLoading = true; _bingoStatus = "Starting.";
        try
        {
            await _bingoApi!.StartGameAsync(_bingoState.game.game_id);
            _bingoState = await _bingoApi.GetStateAsync(_bingoState.game.game_id);
            _bingoStatus = "Game started.";
        }
        catch (Exception ex) { _bingoStatus = $"Failed: {ex.Message}"; }
        finally { _bingoLoading = false; }
    }

    private async Task Bingo_AdvanceStage()
    {
        if (_bingoState is null) return;
        Bingo_EnsureClient();
        _bingoLoading = true; _bingoStatus = "Advancing.";
        try
        {
            await _bingoApi!.AdvanceStageAsync(_bingoState.game.game_id);
            _bingoState = await _bingoApi.GetStateAsync(_bingoState.game.game_id);
            _bingoStatus = "Stage advanced.";
        }
        catch (Exception ex) { _bingoStatus = $"Failed: {ex.Message}"; }
        finally { _bingoLoading = false; }
    }

    private async Task Bingo_ApproveClaim(string? cardId)
    {
        if (_bingoState is null || string.IsNullOrWhiteSpace(cardId)) return;
        Bingo_EnsureClient();
        _bingoLoading = true; _bingoStatus = "Approving.";
        try
        {
            await _bingoApi!.ApproveClaimAsync(_bingoState.game.game_id, cardId);
            await _bingoApi.AdvanceStageAsync(_bingoState.game.game_id);
            _bingoState = await _bingoApi.GetStateAsync(_bingoState.game.game_id);
            _bingoStatus = "Claim approved.";
        }
        catch (Exception ex) { _bingoStatus = $"Failed: {ex.Message}"; }
        finally { _bingoLoading = false; }
    }

    private async Task Bingo_DenyClaim(string? cardId)
    {
        if (_bingoState is null || string.IsNullOrWhiteSpace(cardId)) return;
        Bingo_EnsureClient();
        _bingoLoading = true; _bingoStatus = "Denying.";
        try
        {
            await _bingoApi!.DenyClaimAsync(_bingoState.game.game_id, cardId);
            _bingoState = await _bingoApi.GetStateAsync(_bingoState.game.game_id);
            _bingoStatus = "Claim denied.";
        }
        catch (Exception ex) { _bingoStatus = $"Failed: {ex.Message}"; }
        finally { _bingoLoading = false; }
    }

    private async Task Bingo_LoadOwners()
    {
        if (_bingoState is null) return;
        Bingo_EnsureClient();
        try
        {
            var response = await _bingoApi!.GetOwnersAsync(_bingoState.game.game_id);
            _bingoOwners = response.owners?.ToList() ?? new List<OwnerSummary>();
        }
        catch (Exception ex)
        {
            _bingoStatus = $"Owners failed: {ex.Message}";
            _bingoOwners = new List<OwnerSummary>();
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
        Bingo_EnsureClient();
        _bingoLoading = true; _bingoStatus = $"Buying {count} card(s) for {owner}.";

        try
        {
            await _bingoApi!.BuyAsync(_bingoState.game.game_id, owner, count);
            await Bingo_LoadOwnerCards(owner);
            await Bingo_LoadOwners();
            _bingoStatus = $"Bought {count} for {owner}.";
        }
        catch (Exception ex) { _bingoStatus = $"Buy failed: {ex.Message}"; }
        finally { _bingoLoading = false; }
    }
}









