using Dalamud.Bindings.ImGui; // API 13 ImGui bindings
using Dalamud.Game.ClientState;
using Dalamud.Game.ClientState.Objects;
using Dalamud.Game.ClientState.Objects.SubKinds;
using Dalamud.Game.Text;
using Dalamud.Game.Text.SeStringHandling;
using Dalamud.Game.Gui.ContextMenu;
using Dalamud.Interface.Utility.Raii;
using Dalamud.Interface.Textures;
using Dalamud.Interface.Windowing;
using Dalamud.Plugin.Services;

using Forest.Features.BingoAdmin;
using Forest.Features.CardgamesHost;
using Forest.Features.HuntStaffed;

using System;
using System.Collections.Generic;
using System.Diagnostics;
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
using System.Globalization;

using ImGuiWindowFlags = Dalamud.Bindings.ImGui.ImGuiWindowFlags;

namespace Forest.Windows;

public class MainWindow : Window, IDisposable
{
    private readonly Plugin Plugin;

    // ---------- View switch ----------
    private enum View { Home, Hunt, MurderMystery, Bingo, Raffle, SpinWheel, Glam, Cardgames }
    private enum TopView { Sessions, Games, Players }
    private enum SessionCategory { All, Party, Casino, Draw }
    private enum SessionStatusFilter { All, Live, Waiting, Finished }
    private View _view = View.Home;
    private TopView _topView = TopView.Sessions;
    private bool _controlSurfaceOpen = false;
    private float _controlSurfaceAnim = 0f;
    private string _connectRequiredGame = "";
    private string _gameDetailsText = "";
    private SessionEntry? _selectedSession;
    private string _lastCopyId = "";
    private DateTime _lastCopyAt = DateTime.MinValue;
    private SessionCategory _sessionFilterCategory = SessionCategory.All;
    private SessionStatusFilter _sessionFilterStatus = SessionStatusFilter.All;
    private enum BingoUiState { NoGameLoaded, Ready, Running, StageComplete, Finished }

    // ---------- Left pane layout ----------
    private float _leftPaneWidth = 360f;   // resize via slider (stable with API 13 Columns)
    private float _leftSplitRatio = 0.60f; // Players(top) / Saved(bottom)
    private const float SplitterThickness = 6f;
    private const float SplitterMinTop = 120f;
    private const float SplitterMinBottom = 120f;
    private const float VerticalSplitterThickness = 6f;
    private bool _rightPaneCollapsed = false;

    // ---------- Players (nearby, live) ----------
    private string[] _nearbyPlayers = Array.Empty<string>();
    private string? _selectedOwner;
    private string _selectedSessionId = "";

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
    private string? _bingoApiBaseUrl;
    private string? _bingoApiKey;
    private CancellationTokenSource? _bingoCts;
    private string _bingoStatus = "";
    private bool _bingoLoading = false;
    private string _bingoGameId = "";
    private GameStateEnvelope? _bingoState;
    private readonly Dictionary<string, List<CardInfo>> _bingoOwnerCards = new();
    private List<OwnerSummary> _bingoOwners = new();
    private const int BingoRandomMax = 40;
    private int _bingoRollAttempts = 0;
    private DateTime _bingoRandomCooldownUntil = DateTime.MinValue;
    private string _bingoRandomAllowPick = "";
    private string _bingoRandomAllowManual = "";
    private bool _bingoShowBuyLink = false;
    private string _bingoBuyLink = "";
    private string _bingoBuyOwner = "";
    private string _bingoBuyOwnerInput = "";
    private int _bingoBuyQty = 1;
    private bool _bingoCountsTowardPot = true;
    private int _bingoSeedPotAmount = 0;
    private int _bingoUiTabIndex = 0;
    private bool _bingoCompactMode = false;
    private float _bingoUiScale = 1.0f;
    private bool _bingoAnnounceCalls = false;
    private bool _bingoAutoRoll = false;
    private bool _bingoAutoPinch = false;
    private bool _bingoTabSelectionPending = true;
    private string _bingoCardsExpandedOwner = "";
    private string _bingoOwnerFilter = "";
    private string _bingoOwnerFilterCache = "";
    private readonly List<OwnerSummary> _bingoFilteredOwners = new();
    private bool _bingoOwnersDirty = true;
    private readonly List<string> _bingoActionLog = new();
    private string _bingoLastAction = "";
    private readonly Dictionary<string, string> _bingoOwnerClaimStatus = new(StringComparer.OrdinalIgnoreCase);
    private ISharedImmediateTexture? _homeIconTexture;
    private string? _homeIconPath;
    private string _raffleStatus = "";
    private string _wheelStatus = "";
    private string _glamStatus = "";
    private HuntAdminApiClient? _huntApi;
    private HuntStateResponse? _huntState;
    private string _huntStatus = "";
    private string _huntJoinCode = "";
    private string _huntStaffName = "";
    private string _huntStaffId = "";
    private string _huntId = "";
    private string _huntGroupCode = "";
    private string _huntSelectedCheckpointId = "";
    private DateTime _huntLastRefresh = DateTime.MinValue;
    private List<HuntInfo> _huntList = new();
    private bool _huntLoading = false;
    private int _huntMode = 0; // 0 = Host, 1 = Staff
    private string _huntTitle = "";
    private string _huntDescription = "";
    private string _huntRules = "";
    private bool _huntAllowImplicit = true;

    // ---------- Cardgames (Host) ----------
    private CardgamesHostApiClient? _cardgamesApi;
    private string? _cardgamesApiBaseUrl;
    private string? _cardgamesApiKey;
    private string _cardgamesStatus = "";
    private bool _cardgamesLoading = false;
    private bool _cardgamesDecksLoading = false;
    private string _cardgamesGameId = "blackjack";
    private readonly List<CardgameSession> _cardgamesSessions = new();
    private readonly List<CardDeck> _cardgamesDecks = new();
    private CardgameSession? _cardgamesSelectedSession;
    private string _cardgamesSelectedDeckId = "";
    private int _cardgamesPot = 0;
    private string _cardgamesCurrency = "gil";
    private string _cardgamesBackgroundUrl = "";
    private string _cardgamesLastJoinCode = "";
    private string _cardgamesLastPriestessToken = "";
    private DateTime _cardgamesLastRefresh = DateTime.MinValue;
    private DateTime _cardgamesStateLastFetch = DateTime.MinValue;
    private JsonDocument? _cardgamesStateDoc;
    private string _cardgamesStateError = "";
    private bool _cardgamesStateLoading = false;
    private readonly Dictionary<string, string> _cardgamesPlayerTokens = new();
    private readonly Dictionary<string, ISharedImmediateTexture> _cardgamesTextureCache = new();
    private readonly Dictionary<string, Task> _cardgamesTextureTasks = new();
    private readonly HttpClient _cardgamesHttp = new();
    private bool _permissionsLoading = false;
    private bool _permissionsChecked = false;
    private string _permissionsStatus = "";
    private DateTime _permissionsLastAttempt = DateTime.MinValue;
    private readonly HashSet<string> _allowedScopes = new(StringComparer.OrdinalIgnoreCase);

    public MainWindow(Plugin plugin)
        : base("Forest Manager##Main", ImGuiWindowFlags.NoScrollbar | ImGuiWindowFlags.NoScrollWithMouse | ImGuiWindowFlags.MenuBar)
    {
        Plugin = plugin;
        var baseDir = Forest.Plugin.PluginInterface.AssemblyLocation.DirectoryName ?? string.Empty;
        _homeIconPath = Path.Combine(baseDir, "Resources", "icon.png");
        if (File.Exists(_homeIconPath))
            _homeIconTexture = Forest.Plugin.TextureProvider.GetFromFile(_homeIconPath);
        _pluginStartTime = DateTime.UtcNow;
        _bingoUiTabIndex = Plugin.Config.BingoUiTabIndex;
        _bingoCompactMode = Plugin.Config.BingoCompactMode;
        _bingoUiScale = Plugin.Config.BingoUiScale;
        _bingoAnnounceCalls = Plugin.Config.BingoAnnounceCalls;
        _bingoAutoRoll = Plugin.Config.BingoAutoRoll;
        _bingoAutoPinch = Plugin.Config.BingoAutoPinch;
        _bingoTabSelectionPending = true;
        _cardgamesSelectedDeckId = Plugin.Config.CardgamesPreferredDeckId ?? "";
        _cardgamesPot = Plugin.Config.CardgamesPreferredPot;
        _cardgamesCurrency = Plugin.Config.CardgamesPreferredCurrency ?? "gil";
        _cardgamesBackgroundUrl = Plugin.Config.CardgamesPreferredBackgroundUrl ?? "";
        if (!string.IsNullOrWhiteSpace(Plugin.Config.CardgamesLastGameId))
            _cardgamesGameId = Plugin.Config.CardgamesLastGameId!;
        _cardgamesHttp.Timeout = TimeSpan.FromSeconds(10);
        _allowedScopes.Clear();

        SizeConstraints = new WindowSizeConstraints
        {
            MinimumSize = new Vector2(900, 560),
            MaximumSize = new Vector2(float.MaxValue, float.MaxValue)
        };

        // Hook timers & chat like the old ForestWindow
        Plugin.Framework.Update += OnFrameworkUpdate;
        Plugin.ChatGui.ChatMessage += OnChatMessage;
        if (Plugin.ContextMenu is not null)
        {
            Plugin.ContextMenu.OnMenuOpened += OnContextMenuOpened;
        }
    }

    public void Dispose()
    {
        Plugin.Framework.Update -= OnFrameworkUpdate;
        Plugin.ChatGui.ChatMessage -= OnChatMessage;
        if (Plugin.ContextMenu is not null)
        {
            Plugin.ContextMenu.OnMenuOpened -= OnContextMenuOpened;
        }

        _bingoCts?.Cancel();
        _bingoApi?.Dispose();
        _huntApi?.Dispose();
        _cardgamesApi?.Dispose();
        _cardgamesHttp.Dispose();
        _cardgamesStateDoc?.Dispose();
    }

    private void OnContextMenuOpened(IMenuOpenedArgs args)
    {
        if (args.Target is not IPlayerCharacter pc)
            return;
        var name = pc.Name?.TextValue ?? string.Empty;
        if (string.IsNullOrWhiteSpace(name))
            return;

        var forestRoot = new MenuItem
        {
            Name = "Forest",
            IsSubmenu = true
        };
        args.AddMenuItem(forestRoot);
        if (!Plugin.Config.BingoConnected || _bingoState is null)
        {
            args.AddMenuItem(new MenuItem
            {
                Name = "Forest: Bingo (load a game first)",
                IsEnabled = false
            });
            return;
        }

        args.AddMenuItem(new MenuItem
        {
            Name = "Forest: Buy 1 Bingo Card",
            OnClicked = argsClicked =>
            {
                _ = Bingo_BuyForOwner(name, 1, false);
                _view = View.Bingo;
                _selectedOwner = name;
            }
        });
        args.AddMenuItem(new MenuItem
        {
            Name = "Forest: Buy 10 Bingo Cards",
            OnClicked = argsClicked =>
            {
                _ = Bingo_BuyForOwner(name, 10, false);
                _view = View.Bingo;
                _selectedOwner = name;
            }
        });
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
            Bingo_AddAction("Refreshed games list");
            if (_bingoState is null && string.IsNullOrWhiteSpace(_bingoGameId))
            {
                var last = Plugin.Config.BingoLastSelectedGameId;
                if (!string.IsNullOrWhiteSpace(last) && _bingoGames.Any(g => g.game_id == last))
                {
                    _bingoGameId = last;
                    _ = Bingo_LoadGame(_bingoGameId);
                }
            }
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

    private void OnFrameworkUpdate(IFramework framework)
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

        if (_view == View.Hunt && _huntState?.hunt != null
            && (DateTime.UtcNow - _huntLastRefresh).TotalSeconds >= 10)
        {
            _huntLastRefresh = DateTime.UtcNow;
            _ = Hunt_LoadState();
        }
        if (_view == View.Cardgames
            && (DateTime.UtcNow - _cardgamesLastRefresh).TotalSeconds >= 10
            && !_cardgamesLoading)
        {
            _ = Cardgames_LoadSessions();
        }
        if (_view == View.Cardgames
            && _cardgamesSelectedSession is not null
            && (DateTime.UtcNow - _cardgamesStateLastFetch).TotalSeconds >= 2
            && !_cardgamesStateLoading)
        {
            _ = Cardgames_LoadState();
        }
    }

    // ========================= DRAW =========================
    public override void Draw()
    {
        float delta = ImGui.GetIO().DeltaTime;
        float target = _controlSurfaceOpen ? 1f : 0f;
        float step = Math.Clamp(delta * 8f, 0f, 1f);
        _controlSurfaceAnim = Math.Clamp(_controlSurfaceAnim + (target - _controlSurfaceAnim) * step, 0f, 1f);

        // Top menu bar with buttons (Hunt / Murder Mystery / Bingo) + Settings to the right
        if (ImGui.BeginMenuBar())
        {
            if (ImGui.Button("Sessions")) _topView = TopView.Sessions;
            ImGui.SameLine();
            if (ImGui.Button("Games")) _topView = TopView.Games;
            ImGui.SameLine();
            if (ImGui.Button("Players")) _topView = TopView.Players;

            // push to right
            float rightEdge = ImGui.GetWindowContentRegionMax().X;
            float settingsW = 220f;
            ImGui.SameLine(0, 0);
            ImGui.SetCursorPosX(Math.Max(0, rightEdge - settingsW));
            if (ImGui.SmallButton(_rightPaneCollapsed ? "▶ Panel" : "◀ Panel"))
                _rightPaneCollapsed = !_rightPaneCollapsed;
            ImGui.SameLine();
            if (ImGui.SmallButton("⚙ Settings"))
                Plugin.ToggleConfigUI();

            ImGui.EndMenuBar();
        }

        ImGui.Separator();

        var avail = ImGui.GetContentRegionAvail();
        float minRight = 260f;
        float minLeft = 240f;
        if (_rightPaneCollapsed)
        {
            _leftPaneWidth = avail.X;
        }
        else
        {
            float maxLeft = Math.Max(minLeft, avail.X - minRight - VerticalSplitterThickness);
            _leftPaneWidth = Math.Clamp(_leftPaneWidth, minLeft, maxLeft);
        }

        ImGui.BeginChild("LeftPaneWrap", new Vector2(_leftPaneWidth, 0), false, ImGuiWindowFlags.NoScrollbar | ImGuiWindowFlags.NoScrollWithMouse);
        DrawLeftPane();
        ImGui.EndChild();

        if (!_rightPaneCollapsed)
        {
            ImGui.SameLine(0, 0);
            ImGui.Button("##SplitMain", new Vector2(VerticalSplitterThickness, avail.Y));
            if (ImGui.IsItemActive() && ImGui.IsMouseDragging(0))
            {
                float delta = ImGui.GetIO().MouseDelta.X;
                _leftPaneWidth = Math.Clamp(_leftPaneWidth + delta, minLeft, avail.X - minRight - VerticalSplitterThickness);
            }

            ImGui.SameLine(0, 0);
            ImGui.BeginChild("RightPane", Vector2.Zero, false, 0);
            switch (_topView)
            {
                case TopView.Games: DrawGamesView(); break;
                case TopView.Players: DrawPlayersView(); break;
                case TopView.Sessions: DrawSessionsControlSurface(); break;
            }
            ImGui.EndChild();
        }
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
        DrawSessionsList();
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
                        _ = Bingo_BuyForOwner(ownerKey, 1, false);
                        _view = View.Bingo;
                    }
                    if (ImGui.MenuItem("Buy 10 Cards"))
                    {
                        _selectedOwner = ownerKey;
                        _ = Bingo_BuyForOwner(ownerKey, 10, false);
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
            ImGui.TextDisabled("Loading--|");
        }

        ImGui.Separator();
        ImGui.Spacing();

        if (_bingoGames.Count == 0)
        {
            ImGui.TextDisabled("No games found. Click Refresh.");
            return;
        }

        var tableFlags = ImGuiTableFlags.RowBg
            | ImGuiTableFlags.BordersInnerV
            | ImGuiTableFlags.Resizable
            | ImGuiTableFlags.ScrollY;
        if (ImGui.BeginTable("BingoGamesTable", 5, tableFlags, new Vector2(0, ImGui.GetContentRegionAvail().Y)))
        {
            ImGui.TableSetupColumn("Name", ImGuiTableColumnFlags.WidthStretch);
            ImGui.TableSetupColumn("State", ImGuiTableColumnFlags.WidthFixed, 54f);
            ImGui.TableSetupColumn("Stage", ImGuiTableColumnFlags.WidthFixed, 70f);
            ImGui.TableSetupColumn("Pot", ImGuiTableColumnFlags.WidthFixed, 60f);
            ImGui.TableSetupColumn("Open", ImGuiTableColumnFlags.WidthFixed, 46f);
            ImGui.TableHeadersRow();

            var clipper = new ImGuiListClipper();
            clipper.Begin(_bingoGames.Count);
            while (clipper.Step())
            {
                for (int i = clipper.DisplayStart; i < clipper.DisplayEnd; i++)
                {
                    var g = _bingoGames[i];
                    var id = g.game_id ?? string.Empty;
                    var title = string.IsNullOrWhiteSpace(g.title) ? id : g.title;
                    bool isLoaded = string.Equals(_bingoState?.game.game_id, id, StringComparison.Ordinal)
                                    || string.Equals(_bingoGameId, id, StringComparison.Ordinal);

                    ImGui.TableNextRow();
                    ImGui.TableNextColumn();
                    ImGui.TextUnformatted(title);
                    if (!string.IsNullOrWhiteSpace(id) && ImGui.IsItemHovered())
                        ImGui.SetTooltip(id);

                    ImGui.TableNextColumn();
                    ImGui.TextUnformatted(g.active ? "Active" : "Ended");

                    ImGui.TableNextColumn();
                    ImGui.TextUnformatted(string.IsNullOrWhiteSpace(g.stage) ? "-" : g.stage);

                    ImGui.TableNextColumn();
                    ImGui.TextUnformatted(g.pot.ToString());

                    ImGui.TableNextColumn();
                    using (var dis = ImRaii.Disabled(isLoaded))
                    {
                        if (ImGui.SmallButton($"Open##game-{id}-{i}"))
                        {
                            _bingoGameId = id;
                            _ = Bingo_LoadGame(_bingoGameId);
                        }
                    }
                }
            }
            ImGui.EndTable();
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
        ImGui.TextUnformatted("Staffed Scavenger Hunt");
        ImGui.Separator();
        ImGui.TextUnformatted("Setup");
        ImGui.Separator();
        if (ImGui.CollapsingHeader("What is this?", ImGuiTreeNodeFlags.DefaultOpen))
        {
            ImGui.TextWrapped("Host creates the hunt and manages the session. Staff claim checkpoints and confirm group check-ins on-site.");
        }

        ImGui.Spacing();

        if (string.IsNullOrWhiteSpace(_huntStaffName))
            _huntStaffName = Plugin.ClientState.LocalPlayer?.Name.TextValue ?? "Staff";

        string[] modes = { "Host", "Staff" };
        ImGui.SetNextItemWidth(180f);
        ImGui.Combo("Mode", ref _huntMode, modes, modes.Length);
        ImGui.SameLine();
        if (ImGui.SmallButton("Refresh list"))
            _ = Hunt_LoadList();

        if (!string.IsNullOrWhiteSpace(_huntStatus))
            ImGui.TextDisabled(_huntStatus);

        ImGui.Spacing();
        if (_huntMode == 0)
        {
            ImGui.TextDisabled("Host");
            ImGui.Separator();

            if (_huntList.Count == 0)
            {
                ImGui.TextDisabled("No hunts loaded. Click Refresh list.");
            }
            else
            {
                foreach (var h in _huntList)
                {
                    var id = h.hunt_id ?? "";
                    if (string.IsNullOrEmpty(id)) continue;
                    bool isActive = string.Equals(_huntId, id, StringComparison.Ordinal);
                    if (ImGui.Selectable($"{h.title}##{id}", isActive))
                    {
                        _huntId = id;
                        _huntJoinCode = h.join_code ?? _huntJoinCode;
                        _ = Hunt_LoadState();
                    }
                }
            }

            ImGui.Spacing();
            ImGui.TextDisabled("Create new hunt");
            ImGui.InputText("Title", ref _huntTitle, 64);
            ImGui.InputTextMultiline("Description", ref _huntDescription, 512, new Vector2(ImGui.GetContentRegionAvail().X, 60));
            ImGui.InputTextMultiline("Rules", ref _huntRules, 512, new Vector2(ImGui.GetContentRegionAvail().X, 60));
            ImGui.Checkbox("Allow implicit groups", ref _huntAllowImplicit);

            using (var dis = ImRaii.Disabled(_huntLoading))
            {
                if (ImGui.Button("Create Hunt"))
                    _ = Hunt_Create();
            }

            if (_huntState?.hunt != null)
            {
                var hunt = _huntState.hunt;
                ImGui.Spacing();
                ImGui.TextUnformatted("Live");
                ImGui.Separator();
                ImGui.Spacing();
                ImGui.Text($"Hunt: {hunt.title} ({hunt.hunt_id})");
                ImGui.Text($"Join code: {hunt.join_code}");
                ImGui.Text($"Status: {(hunt.active ? (hunt.started ? "Active" : "Ready") : "Ended")}");

                using (var dis = ImRaii.Disabled(_huntLoading))
                {
                    if (ImGui.Button("Start"))
                        _ = Hunt_Start();
                    ImGui.SameLine();
                    if (ImGui.Button("End"))
                        _ = Hunt_End();
                }
            }
            return;
        }

        ImGui.TextDisabled("Staff");
        ImGui.Separator();

        ImGui.InputText("Join code", ref _huntJoinCode, 32);
        ImGui.InputText("Staff name", ref _huntStaffName, 64);
        if (ImGui.Button("Join Hunt"))
            _ = Hunt_JoinByCode();

        ImGui.SameLine();
        if (ImGui.SmallButton("Refresh") && !string.IsNullOrWhiteSpace(_huntId))
            _ = Hunt_LoadState();

        if (_huntState?.hunt == null)
            return;

        var staffHunt = _huntState.hunt;
        ImGui.Spacing();
        ImGui.TextUnformatted("Live");
        ImGui.Separator();
        ImGui.Spacing();
        ImGui.Text($"Hunt: {staffHunt.title} ({staffHunt.hunt_id})");
        ImGui.Text($"Join code: {staffHunt.join_code}");
        ImGui.Text($"Status: {(staffHunt.active ? (staffHunt.started ? "Active" : "Ready") : "Ended")}");

        int currentTerritory = (int)Plugin.ClientState.TerritoryType;
        if (staffHunt.territory_id > 0)
        {
            bool territoryOk = currentTerritory == staffHunt.territory_id;
            var tColor = territoryOk ? new Vector4(0.5f, 1f, 0.6f, 1f) : new Vector4(1f, 0.6f, 0.4f, 1f);
            ImGui.TextColored(tColor, $"Territory: {staffHunt.territory_id} (you are {currentTerritory})");
        }

        var staffMe = _huntState.staff?.FirstOrDefault(s => s.staff_id == _huntStaffId);
        if (!string.IsNullOrWhiteSpace(staffMe?.checkpoint_id))
            _huntSelectedCheckpointId = staffMe.checkpoint_id!;

        ImGui.Spacing();
        ImGui.Columns(2, "HuntMain", false);
        ImGui.SetColumnWidth(0, 360f);

        ImGui.TextDisabled("Checkpoints");
        ImGui.Separator();
        ImGui.BeginChild("HuntCheckpoints", new Vector2(0, 220), true, 0);
        var checkpoints = _huntState.checkpoints ?? new List<HuntCheckpoint>();
        if (checkpoints.Count == 0)
        {
            ImGui.TextDisabled("No checkpoints yet.");
        }
        else
        {
            foreach (var cp in checkpoints)
            {
                var cpId = cp.checkpoint_id ?? "";
                if (string.IsNullOrEmpty(cpId)) continue;
                bool isSelected = cpId == _huntSelectedCheckpointId;
                if (ImGui.Selectable($"{cp.label}##{cpId}", isSelected))
                    _huntSelectedCheckpointId = cpId;

                ImGui.SameLine();
                if (ImGui.SmallButton($"Claim##{cpId}"))
                    _ = Hunt_ClaimCheckpoint(cpId);

                bool claimedByMe = !string.IsNullOrWhiteSpace(_huntStaffId)
                    && (cp.claimed_by?.Contains(_huntStaffId) ?? false);
                if (claimedByMe)
                {
                    ImGui.SameLine();
                    ImGui.TextDisabled("[yours]");
                }
            }
        }
        ImGui.EndChild();

        ImGui.NextColumn();
        ImGui.TextDisabled("Check-in");
        ImGui.Separator();
        string checkpointLabel = "(none)";
        if (!string.IsNullOrWhiteSpace(_huntSelectedCheckpointId))
        {
            var cp = checkpoints.FirstOrDefault(c => c.checkpoint_id == _huntSelectedCheckpointId);
            if (cp?.label != null) checkpointLabel = cp.label;
        }
        else if (!string.IsNullOrWhiteSpace(staffMe?.checkpoint_id))
        {
            var cp = checkpoints.FirstOrDefault(c => c.checkpoint_id == staffMe.checkpoint_id);
            if (cp?.label != null) checkpointLabel = cp.label;
        }

        ImGui.Text($"Checkpoint: {checkpointLabel}");
        ImGui.InputText("Group code", ref _huntGroupCode, 32);
        bool canCheckIn = staffHunt.started && staffHunt.active
            && !string.IsNullOrWhiteSpace(_huntStaffId)
            && (!string.IsNullOrWhiteSpace(_huntSelectedCheckpointId) || !string.IsNullOrWhiteSpace(staffMe?.checkpoint_id))
            && !string.IsNullOrWhiteSpace(_huntGroupCode);

        using (var dis = ImRaii.Disabled(!canCheckIn))
        {
            if (ImGui.Button("Confirm Check-in"))
                _ = Hunt_CheckIn();
        }

        ImGui.Columns(1);

        ImGui.Spacing();
        ImGui.TextDisabled("Last check-ins");
        ImGui.Separator();
        var checkins = _huntState.checkins ?? new List<HuntCheckin>();
        if (checkins.Count == 0)
        {
            ImGui.TextDisabled("No check-ins yet.");
        }
        else
        {
            foreach (var checkin in checkins)
            {
                string ts = checkin.ts > 0
                    ? DateTimeOffset.FromUnixTimeSeconds((long)checkin.ts).ToLocalTime().ToString("HH:mm:ss")
                    : "--:--:--";
                ImGui.TextUnformatted($"{ts}  {checkin.group_id} -> {checkin.checkpoint_id} (staff {checkin.staff_id})");
            }
        }
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

        if (ImGui.CollapsingHeader("What is this?", ImGuiTreeNodeFlags.DefaultOpen))
        {
            ImGui.TextWrapped("Use the left player list to add/remove participants. Pick the killer, start the 5-minute voting window, and capture whispers. Timers below control the hint cadence.");
        }

        ImGui.TextUnformatted("Setup");
        ImGui.Separator();
        ImGui.TextDisabled("Murder Mystery Details");
        ImGui.Separator();
        ImGui.Spacing();

        // Title
        string title = game.Title ?? "";
        ImGui.TextUnformatted("Title");
        if (ImGui.InputText("##mm-title", ref title, 256))
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
        ImGui.TextUnformatted("Live");
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

            string display = $"--- {playerName}" +
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
        bool connected = Plugin.Config.BingoConnected;
        float scale = Math.Clamp(_bingoUiScale, 0.85f, 1.25f);
        if (Math.Abs(scale - 1f) > 0.01f)
            ImGui.SetWindowFontScale(scale);

        if (!connected)
        {
            ImGui.TextColored(new Vector4(1f, 0.55f, 0.55f, 1f), "Not connected");
            ImGui.TextDisabled("Set your Auth Token in Settings to connect.");
            if (Math.Abs(scale - 1f) > 0.01f)
                ImGui.SetWindowFontScale(1f);
            return;
        }

        var game = _bingoState?.game;
        var uiState = GetBingoUiState(game);

        if (!string.IsNullOrWhiteSpace(Plugin.Config.BingoServerInfo))
        {
            ImGui.TextDisabled($"Server: {Plugin.Config.BingoServerInfo}");
        }
        if (!string.IsNullOrWhiteSpace(_bingoStatus))
        {
            ImGui.TextDisabled(_bingoStatus);
        }
        if (_bingoLoading)
        {
            ImGui.TextDisabled("Working...");
        }

        if (_bingoShowBuyLink)
        {
            ImGui.OpenPopup("Player link");
            _bingoShowBuyLink = false;
        }
        if (ImGui.BeginPopup("Player link"))
        {
            ImGui.TextUnformatted($"Player: {_bingoBuyOwner}");
            ImGui.SetNextItemWidth(420);
            ImGui.InputText("Link", ref _bingoBuyLink, 1024, ImGuiInputTextFlags.ReadOnly);
            if (ImGui.Button("Copy link"))
                ImGui.SetClipboardText(_bingoBuyLink);
            ImGui.SameLine();
            if (ImGui.Button("Close"))
                ImGui.CloseCurrentPopup();
            ImGui.EndPopup();
        }

        if (game != null)
        {
            ImGui.Spacing();
            DrawBingoGameSummaryLine(game);
        }

        if (uiState == BingoUiState.Running || uiState == BingoUiState.StageComplete)
        {
            DrawBingoLastCallPanel(game);
        }

        if (uiState == BingoUiState.Running && !_bingoLoading && !ImGui.GetIO().WantTextInput)
        {
            if (ImGui.IsKeyPressed(Dalamud.Bindings.ImGui.ImGuiKey.N))
            {
                _ = Bingo_Roll();
            }
        }

        if (ImGui.BeginTabBar("BingoTabs", ImGuiTabBarFlags.FittingPolicyResizeDown))
        {
            if (BeginBingoTab("Game", 0))
            {
                DrawBingoPrimaryActionRow(uiState, game);
                DrawBingoGameTab(game);
                ImGui.EndTabItem();
            }
            if (BeginBingoTab("Players", 1))
            {
                DrawBingoPrimaryActionRow(uiState, game);
                DrawBingoPlayersTab(game);
                ImGui.EndTabItem();
            }
            if (BeginBingoTab("Claims", 2))
            {
                DrawBingoPrimaryActionRow(uiState, game);
                DrawBingoClaimsTab(game);
                ImGui.EndTabItem();
            }
            if (BeginBingoTab("Cards", 3))
            {
                DrawBingoPrimaryActionRow(uiState, game);
                DrawBingoCardsTab(game);
                ImGui.EndTabItem();
            }
            if (BeginBingoTab("History", 4))
            {
                DrawBingoPrimaryActionRow(uiState, game);
                DrawBingoHistoryTab(game);
                ImGui.EndTabItem();
            }
            if (BeginBingoTab("Settings", 5))
            {
                DrawBingoPrimaryActionRow(uiState, game);
                DrawBingoSettingsTab(game);
                ImGui.EndTabItem();
            }
            ImGui.EndTabBar();
        }

        if (Math.Abs(scale - 1f) > 0.01f)
            ImGui.SetWindowFontScale(1f);
    }

    private bool BeginBingoTab(string label, int index)
    {
        var flags = (_bingoTabSelectionPending && _bingoUiTabIndex == index)
            ? ImGuiTabItemFlags.SetSelected
            : ImGuiTabItemFlags.None;
        if (ImGui.BeginTabItem(label, flags))
        {
            SetBingoTabIndex(index);
            _bingoTabSelectionPending = false;
            return true;
        }
        return false;
    }

    private void SetBingoTabIndex(int index)
    {
        if (_bingoUiTabIndex == index)
            return;
        _bingoUiTabIndex = index;
        _bingoTabSelectionPending = false;
        Plugin.Config.BingoUiTabIndex = index;
        Plugin.Config.Save();
    }

    private void SelectBingoTab(int index)
    {
        _bingoUiTabIndex = index;
        _bingoTabSelectionPending = true;
        Plugin.Config.BingoUiTabIndex = index;
        Plugin.Config.Save();
    }

    private void SaveBingoUiSettings()
    {
        Plugin.Config.BingoCompactMode = _bingoCompactMode;
        Plugin.Config.BingoUiScale = _bingoUiScale;
        Plugin.Config.BingoAnnounceCalls = _bingoAnnounceCalls;
        Plugin.Config.BingoAutoRoll = _bingoAutoRoll;
        Plugin.Config.BingoAutoPinch = _bingoAutoPinch;
        Plugin.Config.Save();
    }

    private BingoUiState GetBingoUiState(GameInfo? game)
    {
        if (game == null || _bingoState == null)
            return BingoUiState.NoGameLoaded;
        if (!game.started)
            return BingoUiState.Ready;
        if (game.active)
        {
            bool stageComplete = false;
            var claims = game.claims;
            if (claims != null)
            {
                string stage = game.stage ?? "";
                for (int i = 0; i < claims.Length; i++)
                {
                    var c = claims[i];
                    if (!string.Equals(c.stage ?? "", stage, StringComparison.OrdinalIgnoreCase))
                        continue;
                    if (!c.pending && !c.denied)
                    {
                        stageComplete = true;
                        break;
                    }
                }
            }
            return stageComplete ? BingoUiState.StageComplete : BingoUiState.Running;
        }
        return BingoUiState.Finished;
    }

    private void DrawBingoPrimaryActionRow(BingoUiState state, GameInfo? game)
    {
        string statusText = state switch
        {
            BingoUiState.NoGameLoaded => "No Game Loaded",
            BingoUiState.Ready => "Waiting to Start",
            BingoUiState.Running => "Running",
            BingoUiState.StageComplete => "Stage Complete",
            _ => "Finished"
        };
        Vector4 statusColor = state switch
        {
            BingoUiState.NoGameLoaded => new Vector4(0.45f, 0.45f, 0.45f, 1f),
            BingoUiState.Ready => new Vector4(0.95f, 0.8f, 0.35f, 1f),
            BingoUiState.Running => new Vector4(0.5f, 1f, 0.6f, 1f),
            BingoUiState.StageComplete => new Vector4(0.95f, 0.6f, 0.35f, 1f),
            _ => new Vector4(1f, 0.55f, 0.55f, 1f)
        };

        DrawBingoStatusPill(statusText, statusColor);
        ImGui.SameLine();

        string primaryLabel = state switch
        {
            BingoUiState.NoGameLoaded => "Load Game",
            BingoUiState.Ready => "Start",
            BingoUiState.StageComplete => "Advance Stage",
            BingoUiState.Finished => "Close Game",
            _ => "Call Next Number"
        };

        bool hasGame = game != null;
        bool primaryEnabled = state switch
        {
            BingoUiState.NoGameLoaded => !string.IsNullOrWhiteSpace(_bingoGameId),
            BingoUiState.Ready => hasGame,
            BingoUiState.Running => hasGame && game!.active,
            BingoUiState.StageComplete => hasGame && game!.active,
            BingoUiState.Finished => hasGame,
            _ => false
        };
        string disabledReason = state switch
        {
            BingoUiState.NoGameLoaded => "Select a game from the list or enter a Game Id in Advanced.",
            BingoUiState.Ready => "Load a game first.",
            BingoUiState.Running => "Game must be active.",
            BingoUiState.StageComplete => "Game must be active.",
            BingoUiState.Finished => "Load a game first.",
            _ => "Unavailable."
        };

        using (var dis = ImRaii.Disabled(!primaryEnabled || _bingoLoading))
        {
            if (ImGui.Button(primaryLabel))
            {
                switch (state)
                {
                    case BingoUiState.NoGameLoaded:
                        _ = Bingo_LoadGame(_bingoGameId);
                        break;
                    case BingoUiState.Ready:
                        _ = Bingo_Start();
                        break;
                    case BingoUiState.StageComplete:
                        _ = Bingo_AdvanceStage();
                        break;
                    case BingoUiState.Finished:
                        Bingo_ClearGame();
                        break;
                    case BingoUiState.Running:
                        _ = Bingo_Roll();
                        break;
                }
            }
        }
        if (!primaryEnabled || _bingoLoading)
            DrawDisabledTooltip(_bingoLoading ? "Working..." : disabledReason);

        ImGui.SameLine();
        if (ImGui.SmallButton("More"))
            ImGui.OpenPopup("BingoMoreActions");
        if (ImGui.BeginPopup("BingoMoreActions"))
        {
            bool canRefresh = hasGame;
            using (var dis = ImRaii.Disabled(!canRefresh || _bingoLoading))
            {
                if (ImGui.MenuItem("Refresh Game"))
                    _ = Bingo_LoadGame(game!.game_id);
            }
            if (!canRefresh || _bingoLoading)
                DrawDisabledTooltip("Load a game first.");
            if (ImGui.MenuItem("Refresh List"))
                _ = Bingo_LoadGames();

            ImGui.Separator();
            bool canStart = hasGame && !game!.started && game.active;
            using (var dis = ImRaii.Disabled(!canStart || _bingoLoading))
            {
                if (ImGui.MenuItem("Start"))
                    _ = Bingo_Start();
            }
            if (!canStart || _bingoLoading)
                DrawDisabledTooltip("Game must be active and not started.");

            bool canCall = hasGame && game!.active;
            using (var dis = ImRaii.Disabled(!canCall || _bingoLoading))
            {
                if (ImGui.MenuItem("Call Next Number"))
                    _ = Bingo_Roll();
            }
            if (!canCall || _bingoLoading)
                DrawDisabledTooltip("Game must be active.");

            bool canAdvance = hasGame && game!.active;
            using (var dis = ImRaii.Disabled(!canAdvance || _bingoLoading))
            {
                if (ImGui.MenuItem("Advance Stage"))
                    _ = Bingo_AdvanceStage();
            }
            if (!canAdvance || _bingoLoading)
                DrawDisabledTooltip("Game must be active.");

            bool canEnd = hasGame;
            using (var dis = ImRaii.Disabled(!canEnd || _bingoLoading))
            {
                if (ImGui.MenuItem("End Game"))
                    _ = Bingo_End();
            }
            if (!canEnd || _bingoLoading)
                DrawDisabledTooltip("Load a game first.");

            ImGui.EndPopup();
        }

        ImGui.Spacing();
    }

    private void DrawBingoStatusPill(string label, Vector4 color)
    {
        using var pad = ImRaii.PushStyle(ImGuiStyleVar.FramePadding, new Vector2(10f, 6f));
        using var col = ImRaii.PushColor(ImGuiCol.Button, ImGui.ColorConvertFloat4ToU32(color));
        using var colHover = ImRaii.PushColor(ImGuiCol.ButtonHovered, ImGui.ColorConvertFloat4ToU32(color));
        using var colActive = ImRaii.PushColor(ImGuiCol.ButtonActive, ImGui.ColorConvertFloat4ToU32(color));
        ImGui.Button(label);
    }

    private void DrawDisabledTooltip(string text)
    {
        if (ImGui.IsItemHovered(ImGuiHoveredFlags.AllowWhenDisabled))
            ImGui.SetTooltip(text);
    }

    private void DrawBingoGameSummaryLine(GameInfo game)
    {
        int ownerCount = _bingoOwners?.Count ?? 0;
        string payoutsText = "Payouts unavailable";
        if (game.payouts != null)
        {
            var remainder = game.payouts.remainder.HasValue ? $" R:{FormatGil(game.payouts.remainder.Value)}" : "";
            payoutsText = $"S:{FormatGil(game.payouts.single)} D:{FormatGil(game.payouts.@double)} F:{FormatGil(game.payouts.full)}{remainder}";
        }
        string summary = $"Summary: {game.title} | Stage {game.stage} | Pot {FormatGil(game.pot)} {game.currency} | {payoutsText} | Owners {ownerCount}";
        ImGui.TextUnformatted(summary);
    }

    private void DrawBingoLastCallPanel(GameInfo? game)
    {
        if (game == null)
            return;
        int? lastCalled = game.last_called;
        if ((!lastCalled.HasValue || lastCalled.Value == 0) && game.called is { Length: > 0 })
            lastCalled = game.called[^1];

        var label = lastCalled.HasValue ? FormatBingoCall(lastCalled.Value) : "--";
        var count = game.called?.Length ?? 0;

        ImGui.BeginChild("BingoLastCall", new Vector2(0, 72), true, ImGuiWindowFlags.NoScrollbar);
        ImGui.TextDisabled("Last Call");
        ImGui.SetWindowFontScale(1.8f);
        ImGui.TextUnformatted(label);
        ImGui.SetWindowFontScale(1f);
        ImGui.SameLine();
        ImGui.TextDisabled($"Calls: {count}");
        ImGui.SameLine();
        ImGui.TextDisabled($"Stage: {game.stage}");
        ImGui.SameLine();
        if (ImGui.SmallButton("Copy"))
        {
            ImGui.SetClipboardText(label);
            Bingo_AddAction($"Copied call {label}");
        }
        ImGui.SameLine();
        using (var dis = ImRaii.Disabled(!lastCalled.HasValue))
        {
            if (ImGui.SmallButton("Announce"))
            {
                Plugin.ChatGui.Print($"[Bingo] Call {label}");
                Bingo_AddAction($"Announced {label}");
            }
        }
        ImGui.EndChild();
        ImGui.Spacing();
    }

    private string FormatBingoCall(int value)
    {
        if (value <= 0)
            return "--";
        char letter = value switch
        {
            <= 10 => 'B',
            <= 20 => 'I',
            <= 30 => 'N',
            <= 40 => 'G',
            _ => 'O'
        };
        return $"{letter}-{value}";
    }

    private void UpdateBingoOwnerFilter()
    {
        if (!_bingoOwnersDirty && string.Equals(_bingoOwnerFilterCache, _bingoOwnerFilter, StringComparison.Ordinal))
            return;
        _bingoOwnerFilterCache = _bingoOwnerFilter;
        _bingoOwnersDirty = false;
        _bingoFilteredOwners.Clear();
        var filter = _bingoOwnerFilter.Trim();
        for (int i = 0; i < _bingoOwners.Count; i++)
        {
            var owner = _bingoOwners[i];
            if (string.IsNullOrWhiteSpace(filter) || owner.owner_name.Contains(filter, StringComparison.OrdinalIgnoreCase))
                _bingoFilteredOwners.Add(owner);
        }
    }

    private void DrawBingoGameTab(GameInfo? game)
    {
        if (game == null)
        {
            ImGui.TextDisabled("Select a game from the list on the left.");
            return;
        }

        ImGui.TextUnformatted("Game Summary");
        ImGui.Separator();
        ImGui.TextUnformatted($"Title: {game.title}");
        ImGui.TextUnformatted($"Stage: {game.stage}");
        ImGui.TextUnformatted($"Pot: {FormatGil(game.pot)} {game.currency}");
        if (game.payouts != null)
        {
            var remainder = game.payouts.remainder.HasValue ? $" R:{FormatGil(game.payouts.remainder.Value)}" : "";
            ImGui.TextUnformatted($"Payouts: S:{FormatGil(game.payouts.single)} D:{FormatGil(game.payouts.@double)} F:{FormatGil(game.payouts.full)}{remainder}");
        }
        ImGui.Spacing();

        ImGui.TextUnformatted("Last Action");
        ImGui.TextDisabled(string.IsNullOrWhiteSpace(_bingoLastAction) ? "-" : _bingoLastAction);

        if (!_bingoCompactMode && ImGui.CollapsingHeader("Advanced"))
        {
            ImGui.SetNextItemWidth(260);
            ImGui.InputText("Game Id", ref _bingoGameId, 128);
            using (var dis = ImRaii.Disabled(string.IsNullOrWhiteSpace(_bingoGameId)))
            {
                if (ImGui.Button("Load Game"))
                    _ = Bingo_LoadGame(_bingoGameId);
            }

            ImGui.Spacing();
            ImGui.TextUnformatted("Seed Pot");
            ImGui.SetNextItemWidth(140);
            if (ImGui.SliderInt("Amount", ref _bingoSeedPotAmount, 0, 10000000))
            {
                if (_bingoSeedPotAmount < 0)
                    _bingoSeedPotAmount = 0;
            }
            using (var dis = ImRaii.Disabled(_bingoSeedPotAmount <= 0 || _bingoLoading))
            {
                if (ImGui.Button("Seed"))
                    _ = Bingo_SeedPot(_bingoSeedPotAmount);
            }
        }

        if (!_bingoCompactMode && ImGui.CollapsingHeader("Admin Tools"))
        {
            DrawBingoAllowList(game);
        }
    }

    private void DrawBingoPlayersTab(GameInfo? game)
    {
        if (game == null)
        {
            ImGui.TextDisabled("Select a game from the list on the left.");
            return;
        }

        if (ImGui.InputText("Filter", ref _bingoOwnerFilter, 64))
        {
            _bingoOwnersDirty = true;
        }
        UpdateBingoOwnerFilter();

        var owners = _bingoFilteredOwners.Count > 0 || !string.IsNullOrWhiteSpace(_bingoOwnerFilter)
            ? _bingoFilteredOwners
            : _bingoOwners;

        if (owners.Count == 0)
        {
            ImGui.TextDisabled("No owners loaded yet.");
        }
        else
        {
            var tableFlags = ImGuiTableFlags.RowBg
                | ImGuiTableFlags.BordersInnerV
                | ImGuiTableFlags.Resizable
                | ImGuiTableFlags.ScrollY;
            if (ImGui.BeginTable("BingoOwnersTable", 4, tableFlags, new Vector2(0, 220)))
            {
                ImGui.TableSetupColumn("Name", ImGuiTableColumnFlags.WidthStretch);
                ImGui.TableSetupColumn("Cards", ImGuiTableColumnFlags.WidthFixed, 50f);
                ImGui.TableSetupColumn("Status", ImGuiTableColumnFlags.WidthFixed, 110f);
                ImGui.TableSetupColumn("Actions", ImGuiTableColumnFlags.WidthFixed, 90f);
                ImGui.TableHeadersRow();

                _bingoOwnerClaimStatus.Clear();
                var claims = game.claims;
                if (claims != null)
                {
                    for (int i = 0; i < claims.Length; i++)
                    {
                        var c = claims[i];
                        var name = c.owner_name ?? "";
                        if (string.IsNullOrWhiteSpace(name))
                            continue;
                        if (c.pending)
                            _bingoOwnerClaimStatus[name] = "Claim pending";
                        else if (c.denied)
                            _bingoOwnerClaimStatus[name] = "Claim denied";
                        else
                            _bingoOwnerClaimStatus[name] = "Claim approved";
                    }
                }

                var clipper = new ImGuiListClipper();
                clipper.Begin(owners.Count);
                while (clipper.Step())
                {
                    for (int i = clipper.DisplayStart; i < clipper.DisplayEnd; i++)
                    {
                        var owner = owners[i];
                        ImGui.TableNextRow();
                        ImGui.TableNextColumn();
                        ImGui.TextUnformatted(owner.owner_name);
                        ImGui.TableNextColumn();
                        ImGui.TextUnformatted(owner.cards.ToString());
                        ImGui.TableNextColumn();
                        _bingoOwnerClaimStatus.TryGetValue(owner.owner_name, out var statusText);
                        ImGui.TextUnformatted(string.IsNullOrWhiteSpace(statusText) ? "-" : statusText);
                        ImGui.TableNextColumn();
                        if (ImGui.SmallButton($"View Cards ({owner.cards})##owner-{i}"))
                        {
                            _ = Bingo_LoadOwnerCards(owner.owner_name);
                            _bingoCardsExpandedOwner = owner.owner_name;
                            SelectBingoTab(3);
                        }
                    }
                }
                ImGui.EndTable();
            }
        }

        if (!_bingoCompactMode && ImGui.CollapsingHeader("Advanced"))
        {
            ImGui.TextUnformatted("Buy Cards");
            if (string.IsNullOrWhiteSpace(_bingoBuyOwnerInput) && !string.IsNullOrWhiteSpace(_selectedOwner))
                _bingoBuyOwnerInput = _selectedOwner;

            if (owners.Count > 0)
            {
                string display = string.IsNullOrWhiteSpace(_bingoBuyOwnerInput) ? "Select owner" : _bingoBuyOwnerInput;
                if (ImGui.BeginCombo("Owner", display))
                {
                    for (int i = 0; i < owners.Count; i++)
                    {
                        var o = owners[i];
                        bool selected = string.Equals(_bingoBuyOwnerInput, o.owner_name, StringComparison.OrdinalIgnoreCase);
                        if (ImGui.Selectable(o.owner_name, selected))
                            _bingoBuyOwnerInput = o.owner_name;
                        if (selected) ImGui.SetItemDefaultFocus();
                    }
                    ImGui.EndCombo();
                }
            }
            else
            {
                ImGui.InputText("Owner name", ref _bingoBuyOwnerInput, 128);
            }

            ImGui.SetNextItemWidth(120);
            ImGui.SliderInt("Quantity", ref _bingoBuyQty, 1, 10);
            if (_bingoBuyQty < 1) _bingoBuyQty = 1;
            ImGui.Checkbox("Counts toward pot", ref _bingoCountsTowardPot);

            bool canBuy = !string.IsNullOrWhiteSpace(_bingoBuyOwnerInput);
            using (var dis = ImRaii.Disabled(!canBuy || _bingoLoading))
            {
                if (ImGui.Button("Buy"))
                    _ = Bingo_BuyForOwner(_bingoBuyOwnerInput, _bingoBuyQty, !_bingoCountsTowardPot);
            }
            if (!canBuy || _bingoLoading)
                DrawDisabledTooltip("Select an owner and quantity.");
        }
    }

    private void DrawBingoClaimsTab(GameInfo? game)
    {
        if (game == null)
        {
            ImGui.TextDisabled("Select a game from the list on the left.");
            return;
        }

        var claims = game.claims ?? Array.Empty<Claim>();
        if (claims.Length == 0)
        {
            ImGui.TextDisabled("No claims.");
            return;
        }

        var tableFlags = ImGuiTableFlags.RowBg
            | ImGuiTableFlags.BordersInnerV
            | ImGuiTableFlags.Resizable
            | ImGuiTableFlags.ScrollY;
        if (ImGui.BeginTable("BingoClaimsTable", 6, tableFlags, new Vector2(0, 260)))
        {
            ImGui.TableSetupColumn("Player", ImGuiTableColumnFlags.WidthStretch);
            ImGui.TableSetupColumn("Claim", ImGuiTableColumnFlags.WidthFixed, 110f);
            ImGui.TableSetupColumn("Time", ImGuiTableColumnFlags.WidthFixed, 70f);
            ImGui.TableSetupColumn("Approve", ImGuiTableColumnFlags.WidthFixed, 60f);
            ImGui.TableSetupColumn("Reject", ImGuiTableColumnFlags.WidthFixed, 60f);
            ImGui.TableSetupColumn("Show", ImGuiTableColumnFlags.WidthFixed, 50f);
            ImGui.TableHeadersRow();

            var clipper = new ImGuiListClipper();
            clipper.Begin(claims.Length);
            while (clipper.Step())
            {
                for (int i = clipper.DisplayStart; i < clipper.DisplayEnd; i++)
                {
                    var c = claims[i];
                    var owner = c.owner_name ?? "-";
                    var claimText = _bingoCompactMode ? (c.stage ?? "-") : (c.card_id ?? "-");
                    var tsText = "-";
                    if (c.ts.HasValue && c.ts.Value > 0)
                    {
                        var dt = DateTimeOffset.FromUnixTimeSeconds(c.ts.Value).ToLocalTime();
                        tsText = dt.ToString("HH:mm");
                    }
                    bool pending = c.pending;
                    bool hasCardId = !string.IsNullOrWhiteSpace(c.card_id);

                    ImGui.TableNextRow();
                    ImGui.TableNextColumn();
                    ImGui.TextUnformatted(owner);
                    ImGui.TableNextColumn();
                    ImGui.TextUnformatted(claimText);
                    if (!_bingoCompactMode && !string.IsNullOrWhiteSpace(c.card_id) && ImGui.IsItemHovered())
                        ImGui.SetTooltip(c.card_id);
                    ImGui.TableNextColumn();
                    ImGui.TextUnformatted(tsText);
                    ImGui.TableNextColumn();
                    using (var dis = ImRaii.Disabled(!pending || !hasCardId || _bingoLoading))
                    {
                        if (ImGui.SmallButton($"Approve##claim-{i}"))
                            _ = Bingo_ApproveClaim(c.card_id);
                    }
                    if (!pending || !hasCardId || _bingoLoading)
                        DrawDisabledTooltip(hasCardId ? "Claim must be pending." : "Card id required.");

                    ImGui.TableNextColumn();
                    using (var dis = ImRaii.Disabled(!pending || !hasCardId || _bingoLoading))
                    {
                        if (ImGui.SmallButton($"Reject##claim-{i}"))
                            _ = Bingo_DenyClaim(c.card_id);
                    }
                    if (!pending || !hasCardId || _bingoLoading)
                        DrawDisabledTooltip(hasCardId ? "Claim must be pending." : "Card id required.");

                    ImGui.TableNextColumn();
                    using (var dis = ImRaii.Disabled(string.IsNullOrWhiteSpace(c.owner_name)))
                    {
                        if (ImGui.SmallButton($"Show##claim-show-{i}"))
                            _ = Bingo_LoadOwnerCards(c.owner_name ?? "");
                    }
                }
            }
            ImGui.EndTable();
        }
    }

    private void DrawBingoCardsTab(GameInfo? game)
    {
        if (game == null)
        {
            ImGui.TextDisabled("Select a game from the list on the left.");
            return;
        }

        if (_bingoOwnerCards.Count == 0)
        {
            ImGui.TextDisabled("No cards loaded. Select a player in Players to load cards.");
            return;
        }

        if (!string.IsNullOrWhiteSpace(_bingoCardsExpandedOwner))
        {
            if (!_bingoOwnerCards.TryGetValue(_bingoCardsExpandedOwner, out var cards))
            {
                ImGui.TextDisabled("Selected player has no loaded cards.");
                return;
            }
            string header = _bingoCompactMode ? _bingoCardsExpandedOwner : $"{_bingoCardsExpandedOwner} ({cards.Count})";
            ImGui.SetNextItemOpen(true, ImGuiCond.Always);
            if (ImGui.CollapsingHeader(header))
            {
                foreach (var card in cards)
                {
                    Bingo_DrawCard(card, game.called ?? Array.Empty<int>());
                    ImGui.Separator();
                }
            }
            return;
        }

        if (_bingoOwnerCards.Count > 1)
        {
            ImGui.TextDisabled("Select a player in Players to view their cards.");
            return;
        }

        foreach (var kv in _bingoOwnerCards)
        {
            string header = _bingoCompactMode ? kv.Key : $"{kv.Key} ({kv.Value.Count})";
            ImGui.SetNextItemOpen(true, ImGuiCond.Always);
            if (ImGui.CollapsingHeader(header))
            {
                foreach (var card in kv.Value)
                {
                    Bingo_DrawCard(card, game.called ?? Array.Empty<int>());
                    ImGui.Separator();
                }
            }
        }
    }

    private sealed class SessionEntry
    {
        public string Id { get; set; } = "";
        public string Name { get; set; } = "";
        public string Status { get; set; } = "";
        public SessionCategory Category { get; set; } = SessionCategory.Party;
        public bool Managed { get; set; } = false;
        public string JoinCode { get; set; } = "";
        public View TargetView { get; set; } = View.Home;
        public CardgameSession? Cardgame { get; set; }
        public string? GameId { get; set; }
        public int? Index { get; set; }
    }

    private void DrawSessionsList()
    {
        ImGui.TextDisabled("Sessions");
        ImGui.SameLine();
        if (ImGui.SmallButton("Refresh"))
        {
            if (!_permissionsChecked)
                _ = Permissions_Load();
            if (CanLoadCardgames()) _ = Cardgames_LoadSessions();
            if (CanLoadBingo()) _ = Bingo_LoadGames();
            if (CanLoadHunt()) _ = Hunt_LoadList();
        }

        ImGui.Spacing();
        if (!_permissionsChecked && !_permissionsLoading)
            _ = Permissions_Load();
        if (_permissionsLoading)
            ImGui.TextDisabled("Checking permissions...");
        else if (!string.IsNullOrWhiteSpace(_permissionsStatus))
            ImGui.TextDisabled(_permissionsStatus);

        ImGui.SetNextItemWidth(120f);
        if (ImGui.BeginCombo("Category", _sessionFilterCategory.ToString()))
        {
            foreach (SessionCategory cat in Enum.GetValues(typeof(SessionCategory)))
            {
                bool selected = _sessionFilterCategory == cat;
                if (ImGui.Selectable(cat.ToString(), selected))
                    _sessionFilterCategory = cat;
            }
            ImGui.EndCombo();
        }
        ImGui.SameLine();
        ImGui.SetNextItemWidth(120f);
        if (ImGui.BeginCombo("Status", _sessionFilterStatus.ToString()))
        {
            foreach (SessionStatusFilter st in Enum.GetValues(typeof(SessionStatusFilter)))
            {
                bool selected = _sessionFilterStatus == st;
                if (ImGui.Selectable(st.ToString(), selected))
                    _sessionFilterStatus = st;
            }
            ImGui.EndCombo();
        }

        ImGui.Separator();
        var sessions = BuildSessionEntries();
        if (sessions.Count == 0)
        {
            ImGui.TextDisabled("No sessions.");
            return;
        }

        var tableFlags = ImGuiTableFlags.RowBg
            | ImGuiTableFlags.BordersInnerV
            | ImGuiTableFlags.Resizable
            | ImGuiTableFlags.ScrollY;
        if (ImGui.BeginTable("SessionsTable", 4, tableFlags, new Vector2(0, ImGui.GetContentRegionAvail().Y)))
        {
            ImGui.TableSetupColumn("Type", ImGuiTableColumnFlags.WidthFixed, 70f);
            ImGui.TableSetupColumn("Game", ImGuiTableColumnFlags.WidthStretch);
            ImGui.TableSetupColumn("Status", ImGuiTableColumnFlags.WidthFixed, 70f);
            ImGui.TableSetupColumn("Mode", ImGuiTableColumnFlags.WidthFixed, 70f);
            ImGui.TableHeadersRow();

            foreach (var s in sessions)
            {
                ImGui.TableNextRow();
                ImGui.TableNextColumn();
                ImGui.TextUnformatted($"{CategoryIcon(s.Category)} {CategoryLabel(s.Category)}");
                ImGui.TableNextColumn();
                if (ImGui.Selectable(s.Name, _selectedSessionId == s.Id))
                {
                    _selectedSessionId = s.Id;
                    SelectSession(s);
                }
                ImGui.TableNextColumn();
                ImGui.TextUnformatted(s.Status);
                ImGui.TableNextColumn();
                ImGui.TextUnformatted(s.Managed ? "Managed" : "Local");
            }
            ImGui.EndTable();
        }
    }

    private static string CategoryLabel(SessionCategory category)
    {
        return category switch
        {
            SessionCategory.Casino => "Casino",
            SessionCategory.Draw => "Draw",
            SessionCategory.Party => "Party",
            _ => "All",
        };
    }

    private static string CategoryIcon(SessionCategory category)
    {
        return category switch
        {
            SessionCategory.Casino => "🎰",
            SessionCategory.Draw => "🎁",
            SessionCategory.Party => "🎉",
            _ => "•",
        };
    }

    private static Vector4 CategoryColor(SessionCategory category)
    {
        return category switch
        {
            SessionCategory.Casino => new Vector4(0.95f, 0.76f, 0.30f, 1.0f),
            SessionCategory.Draw => new Vector4(0.92f, 0.50f, 0.70f, 1.0f),
            SessionCategory.Party => new Vector4(0.40f, 0.78f, 0.62f, 1.0f),
            _ => new Vector4(0.70f, 0.70f, 0.70f, 1.0f),
        };
    }

    private List<SessionEntry> BuildSessionEntries()
    {
        var list = new List<SessionEntry>();

        foreach (var s in _cardgamesSessions)
        {
            if (s is null) continue;
            list.Add(new SessionEntry
            {
                Id = $"cardgame-{s.session_id}",
                Name = $"{FormatCardgamesName(s.game_id)} ({s.join_code})",
                Status = string.IsNullOrWhiteSpace(s.status) ? "Waiting" : s.status,
                Category = SessionCategory.Casino,
                Managed = true,
                JoinCode = s.join_code,
                TargetView = View.Cardgames,
                Cardgame = s,
                GameId = s.game_id
            });
        }

        foreach (var g in _bingoGames)
        {
            var id = g.game_id ?? "";
            var title = string.IsNullOrWhiteSpace(g.title) ? id : g.title;
            list.Add(new SessionEntry
            {
                Id = $"bingo-{id}",
                Name = string.IsNullOrWhiteSpace(title) ? "Bingo" : $"Bingo: {title}",
                Status = g.active ? "Live" : "Finished",
                Category = SessionCategory.Draw,
                Managed = true,
                TargetView = View.Bingo,
                GameId = id
            });
        }

        if (_huntState?.hunt is not null)
        {
            var hunt = _huntState.hunt;
            var status = hunt.active ? "Live" : hunt.ended ? "Finished" : "Waiting";
            list.Add(new SessionEntry
            {
                Id = $"hunt-{hunt.hunt_id}",
                Name = string.IsNullOrWhiteSpace(hunt.title) ? "Scavenger Hunt" : hunt.title,
                Status = status,
                Category = SessionCategory.Party,
                Managed = true,
                JoinCode = hunt.join_code ?? "",
                TargetView = View.Hunt,
                GameId = hunt.hunt_id
            });
        }

        if (Plugin.Config.CurrentGame is not null)
        {
            var mm = Plugin.Config.CurrentGame;
            var status = mm.ActivePlayers?.Count > 0 ? "Live" : "Waiting";
            list.Add(new SessionEntry
            {
                Id = $"murder-{Plugin.Config.CurrentGameIndex}",
                Name = string.IsNullOrWhiteSpace(mm.Title) ? "Murder Mystery" : mm.Title,
                Status = status,
                Category = SessionCategory.Party,
                Managed = false,
                TargetView = View.MurderMystery,
                Index = Plugin.Config.CurrentGameIndex
            });
        }

        if (Plugin.Config.GlamRoulette is not null)
        {
            var glam = Plugin.Config.GlamRoulette;
            var status = glam.RoundActive ? "Live" : "Waiting";
            list.Add(new SessionEntry
            {
                Id = "glam",
                Name = string.IsNullOrWhiteSpace(glam.Title) ? "Glam Competition" : glam.Title,
                Status = status,
                Category = SessionCategory.Party,
                Managed = false,
                TargetView = View.Glam
            });
        }

        if (Plugin.Config.Raffle is not null)
        {
            var raffle = Plugin.Config.Raffle;
            var status = raffle.IsOpen ? "Live" : "Waiting";
            list.Add(new SessionEntry
            {
                Id = "raffle",
                Name = string.IsNullOrWhiteSpace(raffle.Title) ? "Raffle" : raffle.Title,
                Status = status,
                Category = SessionCategory.Draw,
                Managed = false,
                TargetView = View.Raffle
            });
        }

        if (Plugin.Config.SpinWheel is not null)
        {
            list.Add(new SessionEntry
            {
                Id = "wheel",
                Name = string.IsNullOrWhiteSpace(Plugin.Config.SpinWheel.Title) ? "Spin Wheel" : Plugin.Config.SpinWheel.Title,
                Status = "Ready",
                Category = SessionCategory.Draw,
                Managed = false,
                TargetView = View.SpinWheel
            });
        }

        list = list.Where(ApplySessionFilters).ToList();
        return list;
    }

    private bool ApplySessionFilters(SessionEntry entry)
    {
        if (_sessionFilterCategory != SessionCategory.All && entry.Category != _sessionFilterCategory)
            return false;
        if (_sessionFilterStatus != SessionStatusFilter.All)
        {
            var status = (entry.Status ?? "").ToLowerInvariant();
            if (_sessionFilterStatus == SessionStatusFilter.Live && status != "live")
                return false;
            if (_sessionFilterStatus == SessionStatusFilter.Waiting && status != "waiting" && status != "ready" && status != "created")
                return false;
            if (_sessionFilterStatus == SessionStatusFilter.Finished && status != "finished")
                return false;
        }
        return true;
    }

    private void SelectSession(SessionEntry entry)
    {
        _topView = TopView.Sessions;
        _controlSurfaceOpen = true;
        _connectRequiredGame = "";
        _gameDetailsText = "";
        _view = entry.TargetView;
        _selectedSession = entry;

        if (entry.TargetView == View.Cardgames && entry.Cardgame is not null)
        {
            _cardgamesSelectedSession = entry.Cardgame;
            _cardgamesGameId = entry.Cardgame.game_id;
            _cardgamesStateLastFetch = DateTime.MinValue;
            _ = Cardgames_LoadState();
        }
        else if (entry.TargetView == View.Bingo && !string.IsNullOrWhiteSpace(entry.GameId))
        {
            _bingoGameId = entry.GameId;
            _ = Bingo_LoadGame(_bingoGameId);
        }
        else if (entry.TargetView == View.Hunt && !string.IsNullOrWhiteSpace(entry.GameId))
        {
            _huntId = entry.GameId;
            _ = Hunt_LoadState();
        }
        else if (entry.TargetView == View.MurderMystery && entry.Index.HasValue)
        {
            Plugin.Config.CurrentGameIndex = entry.Index.Value;
            Plugin.Config.Save();
        }
    }

    private bool HasAdminKey()
    {
        return !string.IsNullOrWhiteSpace(Plugin.Config.BingoApiKey);
    }

    private bool HasScope(string scope)
    {
        if (_allowedScopes.Contains("*"))
            return true;
        return _allowedScopes.Contains(scope);
    }

    private bool HasAnyScope(params string[] scopes)
    {
        if (_allowedScopes.Contains("*"))
            return true;
        foreach (var scope in scopes)
        {
            if (_allowedScopes.Contains(scope))
                return true;
        }
        return false;
    }

    private bool CanLoadCardgames() => HasAnyScope("cardgames:admin", "tarot:admin");
    private bool CanLoadBingo() => HasScope("bingo:admin");
    private bool CanLoadHunt() => HasScope("hunt:admin");

    private bool HasGamePermissions(string title)
    {
        return title switch
        {
            "Scavenger Hunt" => CanLoadHunt(),
            "Blackjack" => CanLoadCardgames(),
            "Poker" => CanLoadCardgames(),
            "High/Low" => CanLoadCardgames(),
            _ => true,
        };
    }

    private async Task Permissions_Load()
    {
        if (_permissionsLoading)
            return;
        if ((DateTime.UtcNow - _permissionsLastAttempt).TotalSeconds < 5)
            return;

        _permissionsLastAttempt = DateTime.UtcNow;
        _permissionsLoading = true;
        _permissionsStatus = "Checking permissions...";
        _allowedScopes.Clear();

        try
        {
            var apiKey = Plugin.Config.BingoApiKey;
            if (string.IsNullOrWhiteSpace(apiKey))
            {
                _permissionsStatus = "Admin key missing; managed sessions hidden.";
                _permissionsChecked = true;
                return;
            }

            var baseUrl = (Plugin.Config.BingoApiBaseUrl ?? "https://server.thebigtree.life:8443").TrimEnd('/');
            using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(8) };
            using var req = new HttpRequestMessage(HttpMethod.Get, $"{baseUrl}/api/auth/permissions");
            req.Headers.Add("X-API-Key", apiKey);
            using var resp = await http.SendAsync(req).ConfigureAwait(false);
            var payload = await resp.Content.ReadAsStringAsync().ConfigureAwait(false);

            if (!resp.IsSuccessStatusCode)
            {
                _permissionsStatus = $"Permission check failed: {resp.StatusCode}";
                _permissionsChecked = true;
                return;
            }

            using var doc = JsonDocument.Parse(payload);
            if (!doc.RootElement.TryGetProperty("ok", out var okEl) || !okEl.GetBoolean())
            {
                _permissionsStatus = "Permission check failed.";
                _permissionsChecked = true;
                return;
            }

            if (doc.RootElement.TryGetProperty("scopes", out var scopesEl) && scopesEl.ValueKind == JsonValueKind.Array)
            {
                foreach (var scope in scopesEl.EnumerateArray())
                {
                    var val = scope.GetString();
                    if (!string.IsNullOrWhiteSpace(val))
                        _allowedScopes.Add(val);
                }
            }

            _permissionsStatus = _allowedScopes.Count == 0
                ? "No managed scopes available for this key."
                : $"Loaded permissions: {string.Join(", ", _allowedScopes)}";
            _permissionsChecked = true;
        }
        catch (Exception ex)
        {
            _permissionsStatus = $"Permission check failed: {ex.Message}";
            _permissionsChecked = true;
        }
        finally
        {
            _permissionsLoading = false;
        }
    }

    private void DrawConnectRequiredPanel()
    {
        ImGui.TextUnformatted("This game uses the central service");
        if (!string.IsNullOrWhiteSpace(_connectRequiredGame))
            ImGui.TextDisabled(_connectRequiredGame);
        ImGui.Spacing();
        if (ImGui.Button("Add admin key"))
            Plugin.ToggleConfigUI();
        ImGui.SameLine();
        if (ImGui.Button("What does this mean?"))
            _gameDetailsText = "This game requires the admin key to prepare sessions.";
    }

    private void DrawSessionHeader()
    {
        var entry = _selectedSession;
        if (entry == null)
        {
            ImGui.TextUnformatted("Session");
            return;
        }

        ImGui.TextUnformatted(entry.Name);
        ImGui.SameLine();
        ImGui.TextDisabled($"{CategoryIcon(entry.Category)} {CategoryLabel(entry.Category)}");
        ImGui.TextDisabled($"Status: {entry.Status}");
    }

    private void DrawPlayerFunnelBlock()
    {
        ImGui.TextUnformatted("Player funnel");
        ImGui.TextDisabled("Share the join code or open the player page.");
        ImGui.Spacing();

        var share = BuildShareInfo();
        DrawCopyRow("Join code", share.JoinCode, "join-code");
        DrawCopyRow("Player link", share.PlayerLink, "player-link");

        using (var dis = ImRaii.Disabled(string.IsNullOrWhiteSpace(share.PlayerLink)))
        {
            if (ImGui.Button("Open player page"))
                OpenUrl(share.PlayerLink);
        }

        if (!string.IsNullOrWhiteSpace(share.HostLink))
        {
            ImGui.Spacing();
            DrawCopyRow("Host link", share.HostLink, "host-link");
        }
    }

    private void DrawLiveReassuranceBlock()
    {
        var entry = _selectedSession;
        ImGui.TextUnformatted("Live status");
        if (entry == null)
        {
            ImGui.TextDisabled("No session selected.");
            return;
        }
        ImGui.TextDisabled($"Current state: {entry.Status}");
    }

    private void DrawCopyRow(string label, string value, string id)
    {
        ImGui.TextDisabled(label);
        float buttonW = 70f;
        float avail = ImGui.GetContentRegionAvail().X;
        float inputW = Math.Max(160f, avail - buttonW - 12f);
        string display = string.IsNullOrWhiteSpace(value) ? "(not available)" : value;

        ImGui.PushItemWidth(inputW);
        using (var dis = ImRaii.Disabled(string.IsNullOrWhiteSpace(value)))
        {
            ImGui.InputText($"##copy-{id}", ref display, 512, ImGuiInputTextFlags.ReadOnly);
        }
        ImGui.PopItemWidth();
        ImGui.SameLine();
        using (var dis = ImRaii.Disabled(string.IsNullOrWhiteSpace(value)))
        {
            if (ImGui.Button($"Copy##{id}"))
            {
                ImGui.SetClipboardText(value);
                _lastCopyId = id;
                _lastCopyAt = DateTime.UtcNow;
            }
        }
        if (WasRecentlyCopied(id))
        {
            ImGui.SameLine();
            ImGui.TextDisabled("Copied");
        }
    }

    private bool WasRecentlyCopied(string id)
    {
        return _lastCopyId == id && (DateTime.UtcNow - _lastCopyAt).TotalSeconds < 2.5;
    }

    private (string JoinCode, string PlayerLink, string HostLink) BuildShareInfo()
    {
        var entry = _selectedSession;
        if (entry == null)
            return ("", "", "");

        if (entry.TargetView == View.Cardgames && entry.Cardgame is not null)
        {
            var baseUrl = GetCardgamesBaseUrl();
            var joinCode = entry.Cardgame.join_code ?? "";
            var playerLink = string.IsNullOrWhiteSpace(joinCode)
                ? ""
                : $"{baseUrl}/cardgames/{entry.Cardgame.game_id}/session/{joinCode}";
            var hostLink = string.IsNullOrWhiteSpace(joinCode)
                ? ""
                : $"{baseUrl}/cardgames/{entry.Cardgame.game_id}/session/{joinCode}?view=priestess";
            if (!string.IsNullOrWhiteSpace(entry.Cardgame.priestess_token))
                hostLink += $"&token={Uri.EscapeDataString(entry.Cardgame.priestess_token)}";
            return (joinCode, playerLink, hostLink);
        }

        return (entry.JoinCode ?? "", "", "");
    }

    private void OpenUrl(string url)
    {
        if (string.IsNullOrWhiteSpace(url))
            return;
        try
        {
            Process.Start(new ProcessStartInfo
            {
                FileName = url,
                UseShellExecute = true
            });
        }
        catch (Exception ex)
        {
            Plugin.ChatGui.PrintError($"[Forest] Could not open link: {ex.Message}");
        }
    }

    private void DrawSessionsControlSurface()
    {
        if (!_controlSurfaceOpen && _controlSurfaceAnim <= 0.01f)
        {
            ImGui.TextDisabled("Control surface collapsed.");
            return;
        }

        var avail = ImGui.GetContentRegionAvail();
        float width = Math.Max(1f, avail.X * _controlSurfaceAnim);
        ImGui.SetCursorPosX(ImGui.GetCursorPosX() + (avail.X - width));
        ImGui.PushStyleVar(ImGuiStyleVar.Alpha, Math.Clamp(_controlSurfaceAnim, 0f, 1f));
        ImGui.BeginChild("ControlSurface", new Vector2(width, avail.Y), false, 0);

        if (ImGui.SmallButton("Collapse"))
        {
            _controlSurfaceOpen = false;
            ImGui.EndChild();
            ImGui.PopStyleVar();
            return;
        }
        ImGui.Separator();

        if (!string.IsNullOrWhiteSpace(_connectRequiredGame) && !HasAdminKey())
        {
            DrawConnectRequiredPanel();
            ImGui.EndChild();
            ImGui.PopStyleVar();
            return;
        }

        if (!string.IsNullOrWhiteSpace(_gameDetailsText))
        {
            ImGui.TextWrapped(_gameDetailsText);
            ImGui.Spacing();
        }

        DrawSessionHeader();
        ImGui.Spacing();
        DrawPlayerFunnelBlock();
        ImGui.Spacing();
        DrawLiveReassuranceBlock();

        ImGui.Separator();
        switch (_view)
        {
            case View.Cardgames: DrawCardgamesPanel(); break;
            case View.Bingo: DrawBingoAdminPanel(); break;
            case View.Hunt: DrawHuntPanel(); break;
            case View.MurderMystery: DrawMurderMysteryPanel(); break;
            case View.Raffle: DrawRafflePanel(); break;
            case View.SpinWheel: DrawSpinWheelPanel(); break;
            case View.Glam: DrawGlamRoulettePanel(); break;
            default: ImGui.TextDisabled("Select a session."); break;
        }

        ImGui.EndChild();
        ImGui.PopStyleVar();
    }

    private void DrawPlayersView()
    {
        ImGui.TextUnformatted("Players");
        ImGui.Separator();
        if (string.IsNullOrWhiteSpace(_selectedOwner))
        {
            ImGui.TextDisabled("Select a player from the left list.");
            return;
        }
        ImGui.TextUnformatted($"Selected: {_selectedOwner}");
        ImGui.Spacing();
        ImGui.TextDisabled("Use the context menu on the player list for actions.");
    }

    private void DrawGamesView()
    {
        ImGui.TextUnformatted("Games");
        ImGui.TextDisabled("Choose a game template, then prepare or start a session.");
        ImGui.Separator();

        DrawGameSection("🎉 Party Games",
            "Experiences run during gatherings and ceremonies.",
            new[]
            {
                new GameCard("Scavenger Hunt", SessionCategory.Party, true, true, false, "Managed staff-led hunt with shared locations."),
                new GameCard("Murder Mystery", SessionCategory.Party, false, false, false, "Local story and text management."),
                new GameCard("Glam Competition", SessionCategory.Party, false, false, true, "Local voting with themed prompts and online lists.")
            });

        DrawGameSection("🎰 Casino Games",
            "Managed tables with join keys and shared decks.",
            new[]
            {
                new GameCard("Blackjack", SessionCategory.Casino, true, true, true, "Managed blackjack table."),
                new GameCard("Poker", SessionCategory.Casino, true, true, true, "Managed Texas Hold'em table."),
                new GameCard("High/Low", SessionCategory.Casino, true, true, true, "Managed high/low rounds.")
            });

        DrawGameSection("🎁 Draws & Giveaways",
            "Lightweight draws and rolling events.",
            new[]
            {
                new GameCard("Raffle", SessionCategory.Draw, false, false, false, "Local raffle draw."),
                new GameCard("Spin Wheel", SessionCategory.Draw, false, false, false, "Local wheel spin (managed later).")
            });
    }

    private readonly struct GameCard
    {
        public string Title { get; }
        public SessionCategory Category { get; }
        public bool Managed { get; }
        public bool JoinKey { get; }
        public bool InternetAssets { get; }
        public string Details { get; }
        public GameCard(string title, SessionCategory category, bool managed, bool joinKey, bool internetAssets, string details)
        {
            Title = title;
            Category = category;
            Managed = managed;
            JoinKey = joinKey;
            InternetAssets = internetAssets;
            Details = details;
        }
    }

    private void DrawGameSection(string title, string description, GameCard[] cards)
    {
        const float cardRowHeight = 76f;
        var padding = new Vector2(14f, 12f);
        var titleSize = ImGui.CalcTextSize(title);
        var descSize = ImGui.CalcTextSize(description);
        float blockHeight = padding.Y * 2f + titleSize.Y + descSize.Y + 8f
            + cards.Length * (cardRowHeight + 8f);

        ImGui.Spacing();
        ImGui.BeginChild($"Section_{title}", new Vector2(0, blockHeight), false, ImGuiWindowFlags.NoScrollbar | ImGuiWindowFlags.NoScrollWithMouse);
        var draw = ImGui.GetWindowDrawList();
        var pos = ImGui.GetWindowPos();
        var size = ImGui.GetWindowSize();
        var accent = CategoryColor(cards.Length > 0 ? cards[0].Category : SessionCategory.Party);
        var bg = new Vector4(accent.X * 0.15f, accent.Y * 0.15f, accent.Z * 0.15f, 0.85f);
        var border = new Vector4(accent.X, accent.Y, accent.Z, 0.40f);
        draw.AddRectFilled(pos, new Vector2(pos.X + size.X, pos.Y + size.Y), ImGui.ColorConvertFloat4ToU32(bg), 14f);
        draw.AddRect(pos, new Vector2(pos.X + size.X, pos.Y + size.Y), ImGui.ColorConvertFloat4ToU32(border), 14f, 0, 1.2f);

        ImGui.SetCursorPos(padding);
        DrawSectionHeader(title, description);
        ImGui.Spacing();
        foreach (var card in cards)
        {
            DrawGameCard(card, cardRowHeight);
            ImGui.Spacing();
        }
        ImGui.EndChild();
    }

    private void DrawGameCard(GameCard card, float rowHeight)
    {
        ImGui.BeginChild($"GameCard_{card.Title}", new Vector2(0, rowHeight), false, ImGuiWindowFlags.NoScrollbar | ImGuiWindowFlags.NoScrollWithMouse);
        var draw = ImGui.GetWindowDrawList();
        var pos = ImGui.GetWindowPos();
        var size = ImGui.GetWindowSize();
        var accent = CategoryColor(card.Category);
        var bg = new Vector4(0.08f, 0.08f, 0.10f, 0.92f);
        var border = new Vector4(accent.X, accent.Y, accent.Z, 0.55f);
        draw.AddRectFilled(pos, new Vector2(pos.X + size.X, pos.Y + size.Y), ImGui.ColorConvertFloat4ToU32(bg), 10f);
        draw.AddRect(pos, new Vector2(pos.X + size.X, pos.Y + size.Y), ImGui.ColorConvertFloat4ToU32(border), 10f, 0, 1.0f);

        var padding = new Vector2(10f, 8f);
        ImGui.SetCursorPos(padding);
        ImGui.PushStyleVar(ImGuiStyleVar.ItemSpacing, new Vector2(8f, 4f));

        float actionW = 150f;
        float detailsW = 80f;
        float buttonAreaW = actionW + detailsW + 8f;
        float textWrapX = pos.X + size.X - padding.X - buttonAreaW;
        ImGui.PushTextWrapPos(textWrapX);

        ImGui.TextUnformatted(card.Title);
        ImGui.SameLine();
        ImGui.TextDisabled($"{CategoryIcon(card.Category)} {CategoryLabel(card.Category)}");
        ImGui.TextDisabled(card.Details);

        DrawBadgeChip(card.Managed ? "Uses central service" : "Runs from this app", accent);
        if (card.JoinKey)
        {
            ImGui.SameLine();
            DrawBadgeChip("Join key needed", new Vector4(0.85f, 0.55f, 0.25f, 1.0f));
        }
        if (card.InternetAssets)
        {
            ImGui.SameLine();
            DrawBadgeChip("Fetches online assets", new Vector4(0.55f, 0.70f, 0.90f, 1.0f));
        }
        ImGui.PopTextWrapPos();

        float buttonY = (rowHeight - 28f) * 0.5f;
        ImGui.SetCursorPos(new Vector2(size.X - padding.X - buttonAreaW, buttonY));
        string actionLabel = card.Managed ? "Prepare session" : "Start";
        if (DrawPrimaryActionButton(actionLabel, card.Managed, card.Title, new Vector2(actionW, 28f)))
        {
            var targetView = ResolveGameCardView(card.Title);
            if (targetView != View.Home)
                SelectGameCard(card, targetView);
            if (card.Managed && !HasGamePermissions(card.Title))
            {
                _gameDetailsText = "Missing permissions for this game. Check your admin key scopes.";
                _controlSurfaceOpen = true;
                _topView = TopView.Sessions;
                return;
            }
            if (card.Managed && !HasAdminKey())
            {
                _connectRequiredGame = card.Title;
                _controlSurfaceOpen = true;
                _topView = TopView.Sessions;
                return;
            }
            _connectRequiredGame = "";
            _controlSurfaceOpen = true;
            _topView = TopView.Sessions;
            _gameDetailsText = "";
            switch (card.Title)
            {
                case "Scavenger Hunt":
                    _ = Hunt_LoadList();
                    break;
                case "Murder Mystery":
                    break;
                case "Glam Competition":
                    break;
                case "Blackjack":
                    _cardgamesGameId = "blackjack";
                    _ = Cardgames_LoadDecks();
                    _ = Cardgames_LoadSessions();
                    break;
                case "Poker":
                    _cardgamesGameId = "poker";
                    _ = Cardgames_LoadDecks();
                    _ = Cardgames_LoadSessions();
                    break;
                case "High/Low":
                    _cardgamesGameId = "highlow";
                    _ = Cardgames_LoadDecks();
                    _ = Cardgames_LoadSessions();
                    break;
                case "Raffle":
                    break;
                case "Spin Wheel":
                    break;
            }
        }
        ImGui.SameLine();
        if (ImGui.Button($"Details##{card.Title}", new Vector2(detailsW, 28f)))
        {
            _gameDetailsText = card.Details;
            _controlSurfaceOpen = true;
            _topView = TopView.Sessions;
        }
        ImGui.PopStyleVar();
        ImGui.EndChild();
    }

    private void DrawSectionHeader(string title, string description)
    {
        ImGui.SetWindowFontScale(1.1f);
        ImGui.TextUnformatted(title);
        ImGui.SetWindowFontScale(1.0f);
        ImGui.TextDisabled(description);
    }

    private void DrawBadgeChip(string text, Vector4 color)
    {
        var draw = ImGui.GetWindowDrawList();
        var pos = ImGui.GetCursorScreenPos();
        var textSize = ImGui.CalcTextSize(text);
        var pad = new Vector2(6f, 3f);
        var size = new Vector2(textSize.X + pad.X * 2f, textSize.Y + pad.Y * 2f);
        var bg = new Vector4(color.X, color.Y, color.Z, 0.25f);
        var border = new Vector4(color.X, color.Y, color.Z, 0.55f);
        draw.AddRectFilled(pos, new Vector2(pos.X + size.X, pos.Y + size.Y), ImGui.ColorConvertFloat4ToU32(bg), 8f);
        draw.AddRect(pos, new Vector2(pos.X + size.X, pos.Y + size.Y), ImGui.ColorConvertFloat4ToU32(border), 8f, 0, 1f);
        draw.AddText(new Vector2(pos.X + pad.X, pos.Y + pad.Y), ImGui.ColorConvertFloat4ToU32(new Vector4(0.95f, 0.95f, 0.95f, 1f)), text);
        ImGui.Dummy(size);
    }

    private bool DrawPrimaryActionButton(string label, bool managed, string id, Vector2? size = null)
    {
        var baseColor = managed
            ? new Vector4(0.30f, 0.55f, 0.85f, 1.0f)
            : new Vector4(0.35f, 0.70f, 0.50f, 1.0f);
        var hover = new Vector4(baseColor.X + 0.05f, baseColor.Y + 0.05f, baseColor.Z + 0.05f, 1.0f);
        var active = new Vector4(baseColor.X + 0.10f, baseColor.Y + 0.10f, baseColor.Z + 0.10f, 1.0f);

        ImGui.PushStyleColor(ImGuiCol.Button, baseColor);
        ImGui.PushStyleColor(ImGuiCol.ButtonHovered, hover);
        ImGui.PushStyleColor(ImGuiCol.ButtonActive, active);
        ImGui.PushStyleVar(ImGuiStyleVar.FramePadding, new Vector2(12f, 6f));
        bool clicked = size.HasValue
            ? ImGui.Button($"{label}##{id}", size.Value)
            : ImGui.Button($"{label}##{id}");
        ImGui.PopStyleVar();
        ImGui.PopStyleColor(3);
        return clicked;
    }

    private void SelectGameCard(GameCard card, View targetView)
    {
        _view = targetView;
        _selectedSession = new SessionEntry
        {
            Id = $"gamecard-{card.Title}",
            Name = card.Title,
            Status = card.Managed ? "Waiting" : "Ready",
            Category = card.Category,
            Managed = card.Managed,
            TargetView = targetView
        };
        _selectedSessionId = _selectedSession.Id;
    }

    private View ResolveGameCardView(string title)
    {
        return title switch
        {
            "Scavenger Hunt" => View.Hunt,
            "Murder Mystery" => View.MurderMystery,
            "Glam Competition" => View.Glam,
            "Blackjack" => View.Cardgames,
            "Poker" => View.Cardgames,
            "High/Low" => View.Cardgames,
            "Raffle" => View.Raffle,
            "Spin Wheel" => View.SpinWheel,
            _ => View.Home
        };
    }

    private void DrawBadge(string text)
    {
        ImGui.SameLine();
        ImGui.TextDisabled($"[{text}]");
    }

    private void DrawBingoHistoryTab(GameInfo? game)
    {
        ImGui.TextUnformatted("Action Log");
        if (_bingoActionLog.Count == 0)
        {
            ImGui.TextDisabled("No actions yet.");
        }
        else
        {
            for (int i = 0; i < _bingoActionLog.Count; i++)
                ImGui.TextUnformatted(_bingoActionLog[i]);
        }

        ImGui.Spacing();
        ImGui.TextUnformatted("Called Numbers");
        if (game == null || game.called == null || game.called.Length == 0)
        {
            ImGui.TextDisabled("No numbers called.");
            return;
        }

        var calls = game.called;
        var clipper = new ImGuiListClipper();
        clipper.Begin(calls.Length);
        while (clipper.Step())
        {
            for (int i = clipper.DisplayStart; i < clipper.DisplayEnd; i++)
            {
                ImGui.TextUnformatted(FormatBingoCall(calls[i]));
            }
        }
    }

    private void DrawBingoSettingsTab(GameInfo? game)
    {
        _ = game;
        bool changed = false;
        if (ImGui.Checkbox("Compact Mode", ref _bingoCompactMode))
            changed = true;
        ImGui.SameLine();
        ImGui.TextDisabled("Hide advanced/admin tools and raw IDs.");

        if (ImGui.SliderFloat("UI Scale", ref _bingoUiScale, 0.85f, 1.25f))
            changed = true;

        if (ImGui.Checkbox("Auto roll", ref _bingoAutoRoll))
            changed = true;
        if (ImGui.Checkbox("Auto pinch", ref _bingoAutoPinch))
            changed = true;

        if (changed)
            SaveBingoUiSettings();

        ImGui.Spacing();
        if (ImGui.Button("Reset UI Defaults"))
        {
            _bingoCompactMode = false;
            _bingoUiScale = 1.0f;
            _bingoAnnounceCalls = false;
            _bingoAutoRoll = false;
            _bingoAutoPinch = false;
            SaveBingoUiSettings();
        }
    }

    private void DrawBingoAllowList(GameInfo game)
    {
        ImGui.TextUnformatted("Random Allow List");
        var allowGameId = game.game_id;
        var allowList = Bingo_GetRandomAllowList(allowGameId);
        if (allowList.Count == 0)
        {
            ImGui.TextDisabled("No extra players allowed.");
        }
        else
        {
            for (int i = allowList.Count - 1; i >= 0; i--)
            {
                var name = allowList[i];
                ImGui.TextUnformatted(name);
                ImGui.SameLine();
                if (ImGui.SmallButton($"Remove##allow-{name}-{i}"))
                    Bingo_RemoveRandomAllow(allowGameId, name);
            }
        }

        if (_bingoOwners.Count > 0)
        {
            if (string.IsNullOrWhiteSpace(_bingoRandomAllowPick))
                _bingoRandomAllowPick = _bingoOwners[0].owner_name;
            ImGui.SetNextItemWidth(240);
            if (ImGui.BeginCombo("Owner", _bingoRandomAllowPick))
            {
                foreach (var owner in _bingoOwners)
                {
                    var selected = string.Equals(_bingoRandomAllowPick, owner.owner_name, StringComparison.OrdinalIgnoreCase);
                    if (ImGui.Selectable(owner.owner_name, selected))
                        _bingoRandomAllowPick = owner.owner_name;
                    if (selected) ImGui.SetItemDefaultFocus();
                }
                ImGui.EndCombo();
            }
            ImGui.SameLine();
            if (ImGui.Button("Allow /random"))
                Bingo_AddRandomAllow(allowGameId, _bingoRandomAllowPick);
        }

        ImGui.SetNextItemWidth(240);
        ImGui.InputText("Add name", ref _bingoRandomAllowManual, 64);
        ImGui.SameLine();
        if (ImGui.Button("Add"))
        {
            Bingo_AddRandomAllow(allowGameId, _bingoRandomAllowManual);
            _bingoRandomAllowManual = "";
        }
    }

    private void Bingo_AddAction(string message)
    {
        if (string.IsNullOrWhiteSpace(message))
            return;
        var stamp = DateTime.Now.ToString("HH:mm:ss");
        var entry = $"{stamp} - {message}";
        _bingoActionLog.Insert(0, entry);
        if (_bingoActionLog.Count > 5)
            _bingoActionLog.RemoveRange(5, _bingoActionLog.Count - 5);
        _bingoLastAction = message;
    }

    private void Bingo_ClearGame()
    {
        _bingoState = null;
        _bingoGameId = "";
        _bingoOwnerCards.Clear();
        _bingoOwners.Clear();
        _bingoOwnersDirty = true;
        _bingoCardsExpandedOwner = "";
        _bingoStatus = "Game closed.";
        Bingo_AddAction("Closed game");
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

        if (ImGui.CollapsingHeader("What is this?", ImGuiTreeNodeFlags.DefaultOpen))
        {
            ImGui.TextWrapped("Start a raffle, have players join with the join phrase, then close and draw winners.");
        }

        ImGui.TextUnformatted("Forest Raffle Roll");
        ImGui.Separator();
        ImGui.TextUnformatted("Setup");
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
        ImGui.TextUnformatted("Live");
        ImGui.Separator();
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
        if (ImGui.CollapsingHeader("What is this?", ImGuiTreeNodeFlags.DefaultOpen))
        {
            ImGui.TextWrapped("Spin a prompt for the party. Everyone does the prompt, or use punishments for the loser.");
        }


        ImGui.TextUnformatted("Spin the Wheel");
        ImGui.Separator();
        ImGui.TextUnformatted("Setup");
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
        ImGui.TextUnformatted("Live");
        ImGui.Separator();
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
        if (ImGui.CollapsingHeader("What is this?", ImGuiTreeNodeFlags.DefaultOpen))
        {
            ImGui.TextWrapped("Contestants get a random theme and a short timer to build a glam. Open voting and collect chat votes with the keyword.");
        }


        ImGui.TextUnformatted("Glam Roulette");
        ImGui.Separator();
        ImGui.TextUnformatted("Setup");
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
        ImGui.TextUnformatted("Live");
        ImGui.Separator();
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

        ImGui.BeginChild("GlamThemeBox", new Vector2(360, 84), true);
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

    // ========================= Cardgames (Host) =========================
    private void DrawCardgamesPanel()
    {
        ImGui.TextUnformatted("Cardgames (Host)");
        ImGui.Separator();
        ImGui.TextUnformatted("Setup");
        ImGui.Separator();
        ImGui.Spacing();

        ImGui.TextDisabled("Game");
        if (ImGui.RadioButton("Blackjack", _cardgamesGameId == "blackjack"))
        {
            _cardgamesGameId = "blackjack";
            Plugin.Config.CardgamesLastGameId = _cardgamesGameId;
            Plugin.Config.Save();
            _ = Cardgames_LoadSessions();
        }
        ImGui.SameLine();
        if (ImGui.RadioButton("Poker", _cardgamesGameId == "poker"))
        {
            _cardgamesGameId = "poker";
            Plugin.Config.CardgamesLastGameId = _cardgamesGameId;
            Plugin.Config.Save();
            _ = Cardgames_LoadSessions();
        }
        ImGui.SameLine();
        if (ImGui.RadioButton("High/Low", _cardgamesGameId == "highlow"))
        {
            _cardgamesGameId = "highlow";
            Plugin.Config.CardgamesLastGameId = _cardgamesGameId;
            Plugin.Config.Save();
            _ = Cardgames_LoadSessions();
        }

        ImGui.Spacing();
        if (ImGui.Button("Refresh sessions"))
            _ = Cardgames_LoadSessions();
        ImGui.SameLine();
        using (var dis = ImRaii.Disabled(_cardgamesDecksLoading))
        {
            if (ImGui.Button("Load decks"))
                _ = Cardgames_LoadDecks();
        }

        ImGui.Spacing();
        ImGui.Separator();

        ImGui.SetNextItemWidth(240);
        string deckLabel = string.IsNullOrWhiteSpace(_cardgamesSelectedDeckId) ? "(default deck)" : _cardgamesSelectedDeckId;
        if (ImGui.BeginCombo("Deck", deckLabel))
        {
            if (ImGui.Selectable("(default deck)", string.IsNullOrWhiteSpace(_cardgamesSelectedDeckId)))
            {
                _cardgamesSelectedDeckId = "";
                Plugin.Config.CardgamesPreferredDeckId = null;
                Plugin.Config.Save();
            }

            foreach (var deck in _cardgamesDecks)
            {
                var label = string.IsNullOrWhiteSpace(deck.name) ? deck.deck_id : $"{deck.name} ({deck.deck_id})";
                bool selected = string.Equals(_cardgamesSelectedDeckId, deck.deck_id, StringComparison.Ordinal);
                if (ImGui.Selectable(label, selected))
                {
                    _cardgamesSelectedDeckId = deck.deck_id;
                    Plugin.Config.CardgamesPreferredDeckId = _cardgamesSelectedDeckId;
                    Plugin.Config.Save();
                }
            }
            ImGui.EndCombo();
        }

        ImGui.SetNextItemWidth(120);
        int pot = Math.Max(0, _cardgamesPot);
        if (ImGui.InputInt("Pot", ref pot))
        {
            _cardgamesPot = Math.Max(0, pot);
            Plugin.Config.CardgamesPreferredPot = _cardgamesPot;
            Plugin.Config.Save();
        }

        ImGui.SetNextItemWidth(120);
        string currency = _cardgamesCurrency;
        if (ImGui.InputText("Currency", ref currency, 32))
        {
            _cardgamesCurrency = string.IsNullOrWhiteSpace(currency) ? "gil" : currency.Trim();
            Plugin.Config.CardgamesPreferredCurrency = _cardgamesCurrency;
            Plugin.Config.Save();
        }

        ImGui.SetNextItemWidth(320);
        string bgUrl = _cardgamesBackgroundUrl;
        if (ImGui.InputText("Background URL", ref bgUrl, 512))
        {
            _cardgamesBackgroundUrl = bgUrl.Trim();
            Plugin.Config.CardgamesPreferredBackgroundUrl = _cardgamesBackgroundUrl;
            Plugin.Config.Save();
        }

        ImGui.Spacing();
        using (var dis = ImRaii.Disabled(_cardgamesLoading))
        {
            if (ImGui.Button("Create session"))
                _ = Cardgames_CreateSession();
        }
        ImGui.SameLine();
        using (var dis = ImRaii.Disabled(_cardgamesLoading || _cardgamesSelectedSession is null))
        {
            if (ImGui.Button("Create from selected"))
                _ = Cardgames_CloneSelected();
        }

        if (!string.IsNullOrWhiteSpace(_cardgamesStatus))
        {
            ImGui.Spacing();
            ImGui.TextDisabled(_cardgamesStatus);
        }

        if (!string.IsNullOrWhiteSpace(_cardgamesLastJoinCode))
        {
            ImGui.Spacing();
            ImGui.Separator();
            ImGui.TextUnformatted("Latest session");
            ImGui.TextWrapped($"Join code: {_cardgamesLastJoinCode}");
            var baseUrl = GetCardgamesBaseUrl();
            var playerLink = $"{baseUrl}/cardgames/{_cardgamesGameId}/session/{_cardgamesLastJoinCode}";
            var hostLink = $"{baseUrl}/cardgames/{_cardgamesGameId}/session/{_cardgamesLastJoinCode}?view=priestess";
            if (!string.IsNullOrWhiteSpace(_cardgamesLastPriestessToken))
                hostLink += $"&token={Uri.EscapeDataString(_cardgamesLastPriestessToken)}";
            ImGui.TextWrapped($"Player link: {playerLink}");
            ImGui.TextWrapped($"Host link: {hostLink}");
            if (ImGui.Button("Copy join code"))
                ImGui.SetClipboardText(_cardgamesLastJoinCode);
            ImGui.SameLine();
            if (ImGui.Button("Copy player link"))
                ImGui.SetClipboardText(playerLink);
            ImGui.SameLine();
            if (ImGui.Button("Copy host link"))
                ImGui.SetClipboardText(hostLink);
        }

        if (_cardgamesSelectedSession is null)
            return;

        ImGui.Spacing();
        ImGui.Separator();
        ImGui.TextUnformatted("Live");
        if (!string.IsNullOrWhiteSpace(_cardgamesStateError))
            ImGui.TextDisabled(_cardgamesStateError);
        if (_cardgamesStateDoc is null)
        {
            ImGui.TextDisabled("Waiting for state...");
            return;
        }

        var root = _cardgamesStateDoc.RootElement;
        if (!root.TryGetProperty("state", out var state))
        {
            ImGui.TextDisabled("No state payload.");
            return;
        }

        var status = GetString(state, "status");
        var result = GetString(state, "result");
        var stage = GetString(state, "stage");
        var phase = GetString(state, "phase");
        if (!string.IsNullOrWhiteSpace(stage) || !string.IsNullOrWhiteSpace(phase))
            ImGui.TextDisabled($"Stage: {FormatGameLabel(stage != "" ? stage : phase)}");
        if (!string.IsNullOrWhiteSpace(status))
            ImGui.TextDisabled($"Status: {status}");
        if (!string.IsNullOrWhiteSpace(result))
            ImGui.TextDisabled($"Result: {result}");

        ImGui.Spacing();

        if (_cardgamesSelectedSession.game_id == "blackjack")
        {
            DrawCardRow("Player hand", GetCardList(state, "player_hand"));
            ImGui.Spacing();
            DrawCardRow("Dealer hand", GetCardList(state, "dealer_hand"));
            ImGui.Spacing();
            using (var dis = ImRaii.Disabled(status != "live"))
            {
                if (ImGui.Button("Hit"))
                    _ = Cardgames_PlayerAction("hit");
                ImGui.SameLine();
                if (ImGui.Button("Stand"))
                    _ = Cardgames_PlayerAction("stand");
            }
        }
        else if (_cardgamesSelectedSession.game_id == "highlow")
        {
            DrawCardRow("Current", GetCardList(state, "current"));
            ImGui.Spacing();
            DrawCardRow("Revealed", GetCardList(state, "revealed"));
            ImGui.Spacing();
            using (var dis = ImRaii.Disabled(status != "live"))
            {
                if (ImGui.Button("Higher"))
                    _ = Cardgames_HostAction("higher");
                ImGui.SameLine();
                if (ImGui.Button("Lower"))
                    _ = Cardgames_HostAction("lower");
                ImGui.SameLine();
                if (ImGui.Button("Double"))
                    _ = Cardgames_HostAction("double");
                ImGui.SameLine();
                if (ImGui.Button("Stop"))
                    _ = Cardgames_HostAction("stop");
            }
        }
        else if (_cardgamesSelectedSession.game_id == "poker")
        {
            DrawCardRow("Player hand", GetCardList(state, "player_hand"));
            ImGui.Spacing();
            DrawCardRow("Dealer hand", GetCardList(state, "dealer_hand"));
            ImGui.Spacing();
            DrawCardRow("Community", GetCardList(state, "community"));
            ImGui.Spacing();
            using (var dis = ImRaii.Disabled(status != "live"))
            {
                if (ImGui.Button("Advance round"))
                    _ = Cardgames_HostAction("advance");
            }
        }

        ImGui.Spacing();
        using (var dis = ImRaii.Disabled(_cardgamesSelectedSession.status == "live"))
        {
            if (ImGui.Button("Start session"))
                _ = Cardgames_StartSelected();
        }
        ImGui.SameLine();
        using (var dis = ImRaii.Disabled(_cardgamesSelectedSession.status != "live"))
        {
            if (ImGui.Button("Finish session"))
                _ = Cardgames_FinishSelected();
        }
    }

    private void DrawCardgamesSessionsList()
    {
        ImGui.TextDisabled("Cardgame sessions");
        ImGui.Separator();
        if (_cardgamesSessions.Count == 0)
        {
            ImGui.TextDisabled("No sessions yet.");
            return;
        }

        foreach (var s in _cardgamesSessions)
        {
            var label = $"{FormatCardgamesName(s.game_id)} - {s.join_code} - {s.status}";
            if (ImGui.Selectable(label, _cardgamesSelectedSession?.session_id == s.session_id))
            {
                _cardgamesSelectedSession = s;
                _cardgamesStateLastFetch = DateTime.MinValue;
                _ = Cardgames_LoadState();
            }
        }

        if (_cardgamesSelectedSession is null)
            return;

        ImGui.Spacing();
        ImGui.Separator();
        ImGui.TextWrapped($"Selected: {_cardgamesSelectedSession.join_code}");
        var baseUrl = GetCardgamesBaseUrl();
        var playerLink = $"{baseUrl}/cardgames/{_cardgamesSelectedSession.game_id}/session/{_cardgamesSelectedSession.join_code}";
        var hostLink = $"{baseUrl}/cardgames/{_cardgamesSelectedSession.game_id}/session/{_cardgamesSelectedSession.join_code}?view=priestess";
        if (!string.IsNullOrWhiteSpace(_cardgamesSelectedSession.priestess_token))
            hostLink += $"&token={Uri.EscapeDataString(_cardgamesSelectedSession.priestess_token)}";
        if (ImGui.Button("Copy join code"))
            ImGui.SetClipboardText(_cardgamesSelectedSession.join_code);
        ImGui.SameLine();
        if (ImGui.Button("Copy player link"))
            ImGui.SetClipboardText(playerLink);
        ImGui.SameLine();
        if (ImGui.Button("Copy host link"))
            ImGui.SetClipboardText(hostLink);
    }

    private static string FormatCardgamesName(string? gameId)
    {
        return gameId switch
        {
            "blackjack" => "Blackjack",
            "poker" => "Poker",
            "highlow" => "High/Low",
            _ => string.IsNullOrWhiteSpace(gameId) ? "Cardgame" : gameId
        };
    }

    private string GetCardgamesBaseUrl()
    {
        var publicBase = Plugin.Config.CardgamesPublicBaseUrl;
        if (!string.IsNullOrWhiteSpace(publicBase))
            return publicBase.TrimEnd('/');
        return (Plugin.Config.BingoApiBaseUrl ?? "https://server.thebigtree.life:8443").TrimEnd('/');
    }

    private string ResolveCardImageUrl(string? url)
    {
        if (string.IsNullOrWhiteSpace(url))
            return "";
        if (url.StartsWith("http://", StringComparison.OrdinalIgnoreCase)
            || url.StartsWith("https://", StringComparison.OrdinalIgnoreCase))
            return url;
        if (!url.StartsWith("/"))
            url = "/" + url;
        return GetCardgamesBaseUrl() + url;
    }

    private bool TryGetCardTexture(string url, out ISharedImmediateTexture? texture)
    {
        texture = null;
        if (string.IsNullOrWhiteSpace(url))
            return false;
        if (_cardgamesTextureCache.TryGetValue(url, out var cached))
        {
            texture = cached;
            return true;
        }
        if (_cardgamesTextureTasks.ContainsKey(url))
            return false;

        _cardgamesTextureTasks[url] = Task.Run(async () =>
        {
            try
            {
                var cacheDir = Path.Combine(Forest.Plugin.PluginInterface.GetPluginConfigDirectory(), "cardgame-cache");
                Directory.CreateDirectory(cacheDir);
                var hash = HashString(url);
                var ext = Path.GetExtension(new Uri(url).AbsolutePath);
                if (string.IsNullOrWhiteSpace(ext))
                    ext = ".png";
                var filePath = Path.Combine(cacheDir, $"{hash}{ext}");
                if (!File.Exists(filePath))
                {
                    var bytes = await _cardgamesHttp.GetByteArrayAsync(url).ConfigureAwait(false);
                    await File.WriteAllBytesAsync(filePath, bytes).ConfigureAwait(false);
                }
                var tex = Forest.Plugin.TextureProvider.GetFromFile(filePath);
                _cardgamesTextureCache[url] = tex;
            }
            catch (Exception ex)
            {
                Plugin.Log?.Warning($"[Cardgames] Failed to load image {url}: {ex.Message}");
            }
            finally
            {
                _cardgamesTextureTasks.Remove(url);
            }
        });
        return false;
    }

    private static string HashString(string value)
    {
        using var sha1 = SHA1.Create();
        var bytes = Encoding.UTF8.GetBytes(value);
        var hash = sha1.ComputeHash(bytes);
        var sb = new StringBuilder(hash.Length * 2);
        foreach (var b in hash)
            sb.Append(b.ToString("x2"));
        return sb.ToString();
    }

    private static List<JsonElement> GetCardList(JsonElement state, string key)
    {
        try
        {
            if (state.ValueKind != JsonValueKind.Object)
                return new List<JsonElement>();
            if (!state.TryGetProperty(key, out var cards))
                return new List<JsonElement>();
            if (cards.ValueKind == JsonValueKind.Object)
                return new List<JsonElement> { cards };
            if (cards.ValueKind != JsonValueKind.Array)
                return new List<JsonElement>();
            return cards.EnumerateArray().ToList();
        }
        catch
        {
            return new List<JsonElement>();
        }
    }

    private static string GetString(JsonElement root, string key)
    {
        if (root.TryGetProperty(key, out var val) && val.ValueKind == JsonValueKind.String)
            return val.GetString() ?? "";
        return "";
    }

    private static int GetInt(JsonElement root, string key)
    {
        if (root.TryGetProperty(key, out var val) && val.ValueKind == JsonValueKind.Number && val.TryGetInt32(out var num))
            return num;
        return 0;
    }

    private static string FormatGameLabel(string label)
    {
        return string.IsNullOrWhiteSpace(label) ? "--" : label;
    }

    private void DrawCardRow(string label, List<JsonElement> cards)
    {
        ImGui.TextUnformatted(label);
        if (cards.Count == 0)
        {
            ImGui.TextDisabled("No cards.");
            return;
        }

        float cardW = 72f;
        float cardH = 100f;
        for (int i = 0; i < cards.Count; i++)
        {
            var card = cards[i];
            string img = "";
            if (card.TryGetProperty("image", out var imgEl) && imgEl.ValueKind == JsonValueKind.String)
                img = ResolveCardImageUrl(imgEl.GetString());
            var rendered = false;
            if (!string.IsNullOrWhiteSpace(img) && TryGetCardTexture(img, out var tex) && tex is not null)
            {
                var wrap = tex.GetWrapOrDefault();
                if (wrap is not null)
                {
                    ImGui.Image(wrap.Handle, new Vector2(cardW, cardH));
                    rendered = true;
                }
            }
            if (!rendered)
                ImGui.Button("...", new Vector2(cardW, cardH));
            if (i + 1 < cards.Count)
                ImGui.SameLine();
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

            ImGui.SetNextItemWidth(320);
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

            ImGui.SetNextItemWidth(320);
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
        string cardLabel = _bingoCompactMode ? $"Card {n}x{n}" : $"Card {card.card_id} - {n}x{n}";
        ImGui.TextDisabled(cardLabel);
        if (!_bingoCompactMode && !string.IsNullOrWhiteSpace(card.card_id) && ImGui.IsItemHovered())
            ImGui.SetTooltip(card.card_id);

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
        var baseUrl = Plugin.Config.BingoApiBaseUrl ?? "https://server.thebigtree.life:8443";
        var apiKey = Plugin.Config.BingoApiKey;
        var needsRefresh = _bingoApi is null
                           || !string.Equals(_bingoApiBaseUrl, baseUrl, StringComparison.Ordinal)
                           || !string.Equals(_bingoApiKey, apiKey, StringComparison.Ordinal);
        if (!needsRefresh)
            return;

        _bingoApi?.Dispose();
        _bingoApiBaseUrl = baseUrl;
        _bingoApiKey = apiKey;
        _bingoApi = new BingoAdminApiClient(baseUrl, apiKey);
    }

    private static string FormatGil(int value)
    {
        return value.ToString("N0", CultureInfo.InvariantCulture).Replace(",", ".");
    }

    private void Cardgames_EnsureClient()
    {
        var baseUrl = Plugin.Config.BingoApiBaseUrl ?? "https://server.thebigtree.life:8443";
        var apiKey = Plugin.Config.BingoApiKey;
        var needsRefresh = _cardgamesApi is null
                           || !string.Equals(_cardgamesApiBaseUrl, baseUrl, StringComparison.Ordinal)
                           || !string.Equals(_cardgamesApiKey, apiKey, StringComparison.Ordinal);
        if (!needsRefresh)
            return;

        _cardgamesApi?.Dispose();
        _cardgamesApiBaseUrl = baseUrl;
        _cardgamesApiKey = apiKey;
        _cardgamesApi = new CardgamesHostApiClient(baseUrl, apiKey);
    }

    private async Task Cardgames_LoadDecks()
    {
        Cardgames_EnsureClient();
        _cardgamesDecksLoading = true;
        try
        {
            var decks = await _cardgamesApi!.ListDecksAsync();
            _cardgamesDecks.Clear();
            _cardgamesDecks.AddRange(decks.OrderBy(d => d.name ?? d.deck_id));
            if (!string.IsNullOrWhiteSpace(_cardgamesSelectedDeckId)
                && _cardgamesDecks.All(d => d.deck_id != _cardgamesSelectedDeckId))
            {
                _cardgamesSelectedDeckId = "";
                Plugin.Config.CardgamesPreferredDeckId = null;
                Plugin.Config.Save();
            }
            _cardgamesStatus = $"Loaded {_cardgamesDecks.Count} deck(s).";
        }
        catch (Exception ex)
        {
            _cardgamesStatus = $"Failed to load decks: {ex.Message}";
        }
        finally
        {
            _cardgamesDecksLoading = false;
        }
    }

    private async Task Cardgames_LoadSessions()
    {
        if (string.IsNullOrWhiteSpace(_cardgamesGameId))
        {
            _cardgamesStatus = "Select a game first.";
            return;
        }
        Cardgames_EnsureClient();
        _cardgamesLoading = true;
        try
        {
            var sessions = await _cardgamesApi!.ListSessionsAsync(_cardgamesGameId);
            _cardgamesSessions.Clear();
            _cardgamesSessions.AddRange(sessions);
            _cardgamesLastRefresh = DateTime.UtcNow;
            _cardgamesStatus = $"Loaded {_cardgamesSessions.Count} session(s).";
            if (_cardgamesSelectedSession is not null)
            {
                var updated = _cardgamesSessions.FirstOrDefault(s => s.session_id == _cardgamesSelectedSession.session_id);
            _cardgamesSelectedSession = updated;
            if (_cardgamesSelectedSession is not null)
            {
                if (!string.IsNullOrWhiteSpace(_cardgamesSelectedSession.deck_id))
                    _cardgamesSelectedDeckId = _cardgamesSelectedSession.deck_id!;
                if (_cardgamesSelectedSession.pot >= 0)
                    _cardgamesPot = _cardgamesSelectedSession.pot;
                if (!string.IsNullOrWhiteSpace(_cardgamesSelectedSession.currency))
                    _cardgamesCurrency = _cardgamesSelectedSession.currency!;
                if (!string.IsNullOrWhiteSpace(_cardgamesSelectedSession.background_url))
                    _cardgamesBackgroundUrl = _cardgamesSelectedSession.background_url!;
            }
            }
            if (_cardgamesSelectedSession is null && _cardgamesStateDoc is not null)
            {
                _cardgamesStateDoc.Dispose();
                _cardgamesStateDoc = null;
            }
        }
        catch (Exception ex)
        {
            _cardgamesStatus = $"Failed to load sessions: {ex.Message}";
        }
        finally
        {
            _cardgamesLoading = false;
        }
    }

    private async Task Cardgames_CreateSession()
    {
        if (string.IsNullOrWhiteSpace(_cardgamesGameId))
        {
            _cardgamesStatus = "Select a game first.";
            return;
        }
        Cardgames_EnsureClient();
        _cardgamesLoading = true;
        try
        {
            var resp = await _cardgamesApi!.CreateSessionAsync(
                _cardgamesGameId,
                _cardgamesPot,
                _cardgamesSelectedDeckId,
                _cardgamesCurrency,
                _cardgamesBackgroundUrl
            );
            if (!resp.ok || resp.session is null)
            {
                _cardgamesStatus = resp.error ?? "Create failed.";
                return;
            }
            var s = resp.session;
            _cardgamesLastJoinCode = s.join_code;
            _cardgamesLastPriestessToken = s.priestess_token;
            _cardgamesStatus = $"Session created: {s.join_code}.";
            _ = Cardgames_LoadSessions();
        }
        catch (Exception ex)
        {
            _cardgamesStatus = $"Create failed: {ex.Message}";
        }
        finally
        {
            _cardgamesLoading = false;
        }
    }

    private async Task Cardgames_CloneSelected()
    {
        if (_cardgamesSelectedSession is null)
            return;
        Cardgames_EnsureClient();
        _cardgamesStatus = "Cloning session.";
        try
        {
            var resp = await _cardgamesApi!.CloneSessionAsync(
                _cardgamesSelectedSession.game_id,
                _cardgamesSelectedSession.session_id,
                _cardgamesSelectedSession.priestess_token
            );
            if (!resp.ok || resp.session is null)
            {
                _cardgamesStatus = resp.error ?? "Clone failed.";
                return;
            }
            var s = resp.session;
            _cardgamesLastJoinCode = s.join_code;
            _cardgamesLastPriestessToken = s.priestess_token;
            _cardgamesStatus = $"Session cloned: {s.join_code}.";
            _ = Cardgames_LoadSessions();
        }
        catch (Exception ex)
        {
            _cardgamesStatus = $"Clone failed: {ex.Message}";
        }
    }

    private async Task Cardgames_LoadState()
    {
        if (_cardgamesSelectedSession is null)
            return;

        Cardgames_EnsureClient();
        _cardgamesStateLoading = true;
        _cardgamesStateError = "";
        try
        {
            var resp = await _cardgamesApi!.GetStateAsync(_cardgamesSelectedSession.game_id, _cardgamesSelectedSession.join_code);
            if (!resp.ok)
            {
                _cardgamesStateError = resp.error ?? "Failed to load state.";
                return;
            }
            _cardgamesStateDoc?.Dispose();
            _cardgamesStateDoc = JsonDocument.Parse(resp.state.GetRawText());
            _cardgamesStateLastFetch = DateTime.UtcNow;
        }
        catch (Exception ex)
        {
            _cardgamesStateError = $"State load failed: {ex.Message}";
        }
        finally
        {
            _cardgamesStateLoading = false;
        }
    }

    private async Task Cardgames_StartSelected()
    {
        if (_cardgamesSelectedSession is null)
            return;
        Cardgames_EnsureClient();
        _cardgamesStatus = "Starting session.";
        try
        {
            var resp = await _cardgamesApi!.StartSessionAsync(
                _cardgamesSelectedSession.game_id,
                _cardgamesSelectedSession.session_id,
                _cardgamesSelectedSession.priestess_token
            );
            if (!resp.ok)
            {
                _cardgamesStatus = resp.error ?? "Start failed.";
                return;
            }
            _cardgamesStatus = "Session started.";
            _ = Cardgames_LoadSessions();
            _ = Cardgames_LoadState();
        }
        catch (Exception ex)
        {
            _cardgamesStatus = $"Start failed: {ex.Message}";
        }
    }

    private async Task Cardgames_FinishSelected()
    {
        if (_cardgamesSelectedSession is null)
            return;
        Cardgames_EnsureClient();
        _cardgamesStatus = "Finishing session.";
        try
        {
            var resp = await _cardgamesApi!.FinishSessionAsync(
                _cardgamesSelectedSession.game_id,
                _cardgamesSelectedSession.session_id,
                _cardgamesSelectedSession.priestess_token
            );
            if (!resp.ok)
            {
                _cardgamesStatus = resp.error ?? "Finish failed.";
                return;
            }
            _cardgamesStatus = "Session finished.";
            _cardgamesSelectedSession = null;
            _cardgamesStateDoc?.Dispose();
            _cardgamesStateDoc = null;
            _ = Cardgames_LoadSessions();
        }
        catch (Exception ex)
        {
            _cardgamesStatus = $"Finish failed: {ex.Message}";
        }
    }

    private async Task Cardgames_HostAction(string action)
    {
        if (_cardgamesSelectedSession is null)
            return;
        Cardgames_EnsureClient();
        try
        {
            var resp = await _cardgamesApi!.HostActionAsync(
                _cardgamesSelectedSession.game_id,
                _cardgamesSelectedSession.session_id,
                _cardgamesSelectedSession.priestess_token,
                action
            );
            if (!resp.ok)
            {
                _cardgamesStatus = resp.error ?? "Action failed.";
                return;
            }
            _cardgamesStatus = $"Action: {action}.";
            _ = Cardgames_LoadState();
        }
        catch (Exception ex)
        {
            _cardgamesStatus = $"Action failed: {ex.Message}";
        }
    }

    private async Task Cardgames_PlayerAction(string action)
    {
        if (_cardgamesSelectedSession is null)
            return;
        Cardgames_EnsureClient();
        try
        {
            var token = await EnsurePlayerToken(_cardgamesSelectedSession);
            if (string.IsNullOrWhiteSpace(token))
            {
                _cardgamesStatus = "Unable to join session as player.";
                return;
            }
            var resp = await _cardgamesApi!.PlayerActionAsync(
                _cardgamesSelectedSession.game_id,
                _cardgamesSelectedSession.session_id,
                token,
                action
            );
            if (!resp.ok)
            {
                _cardgamesStatus = resp.error ?? "Action failed.";
                return;
            }
            _cardgamesStatus = $"Action: {action}.";
            _ = Cardgames_LoadState();
        }
        catch (Exception ex)
        {
            _cardgamesStatus = $"Action failed: {ex.Message}";
        }
    }

    private async Task<string> EnsurePlayerToken(CardgameSession session)
    {
        if (_cardgamesPlayerTokens.TryGetValue(session.session_id, out var token))
            return token;

        var join = await _cardgamesApi!.JoinSessionAsync(session.game_id, session.join_code);
        if (!join.ok || string.IsNullOrWhiteSpace(join.player_token))
            return "";
        _cardgamesPlayerTokens[session.session_id] = join.player_token;
        return join.player_token;
    }

    private void Hunt_EnsureClient()
    {
        if (_huntApi is not null) return;
        _huntApi = new HuntAdminApiClient(
            Plugin.Config.BingoApiBaseUrl ?? "https://server.thebigtree.life:8443",
            Plugin.Config.BingoApiKey
        );
    }

    private async Task Hunt_JoinByCode()
    {
        if (string.IsNullOrWhiteSpace(_huntJoinCode))
        {
            _huntStatus = "Join code required.";
            return;
        }
        Hunt_EnsureClient();
        _huntStatus = "Joining hunt.";
        try
        {
            var resp = await _huntApi!.JoinByCodeAsync(_huntJoinCode.Trim(), _huntStaffName.Trim(), _huntStaffId);
            if (!resp.ok)
            {
                _huntStatus = resp.error ?? "Join failed.";
                return;
            }
            _huntId = resp.hunt_id ?? "";
            _huntStaffId = resp.staff_id ?? _huntStaffId;
            _huntState = resp.state;
            _huntStatus = "Joined hunt.";
            _huntLastRefresh = DateTime.UtcNow;
        }
        catch (Exception ex)
        {
            _huntStatus = $"Join failed: {ex.Message}";
        }
    }

    private async Task Hunt_LoadState()
    {
        if (string.IsNullOrWhiteSpace(_huntId))
        {
            _huntStatus = "Join a hunt first.";
            return;
        }
        Hunt_EnsureClient();
        _huntStatus = "Refreshing hunt state.";
        try
        {
            _huntState = await _huntApi!.GetStateAsync(_huntId);
            _huntStatus = "Hunt state updated.";
        }
        catch (Exception ex)
        {
            _huntStatus = $"Refresh failed: {ex.Message}";
        }
    }

    private async Task Hunt_LoadList()
    {
        Hunt_EnsureClient();
        _huntLoading = true;
        try
        {
            var resp = await _huntApi!.ListHuntsAsync();
            _huntList = resp.hunts ?? new List<HuntInfo>();
            _huntStatus = $"Loaded {_huntList.Count} hunt(s).";
        }
        catch (Exception ex)
        {
            _huntStatus = $"Failed to load hunts: {ex.Message}";
            _huntList = new List<HuntInfo>();
        }
        finally
        {
            _huntLoading = false;
        }
    }

    private async Task Hunt_Create()
    {
        Hunt_EnsureClient();
        _huntLoading = true;
        try
        {
            int territoryId = (int)Plugin.ClientState.TerritoryType;
            var resp = await _huntApi!.CreateHuntAsync(
                _huntTitle.Trim(),
                territoryId,
                _huntDescription.Trim(),
                _huntRules.Trim(),
                _huntAllowImplicit
            );
            if (!resp.ok || resp.hunt == null)
            {
                _huntStatus = resp.error ?? "Failed to create hunt.";
                return;
            }
            _huntId = resp.hunt.hunt_id ?? "";
            _huntJoinCode = resp.hunt.join_code ?? "";
            _huntStatus = $"Created hunt '{resp.hunt.title}'.";
            await Hunt_LoadState();
            await Hunt_LoadList();
        }
        catch (Exception ex)
        {
            _huntStatus = $"Create failed: {ex.Message}";
        }
        finally
        {
            _huntLoading = false;
        }
    }

    private async Task Hunt_Start()
    {
        if (string.IsNullOrWhiteSpace(_huntId))
        {
            _huntStatus = "Select a hunt first.";
            return;
        }
        Hunt_EnsureClient();
        _huntLoading = true;
        try
        {
            await _huntApi!.StartAsync(_huntId);
            await Hunt_LoadState();
            _huntStatus = "Hunt started.";
        }
        catch (Exception ex)
        {
            _huntStatus = $"Start failed: {ex.Message}";
        }
        finally
        {
            _huntLoading = false;
        }
    }

    private async Task Hunt_End()
    {
        if (string.IsNullOrWhiteSpace(_huntId))
        {
            _huntStatus = "Select a hunt first.";
            return;
        }
        Hunt_EnsureClient();
        _huntLoading = true;
        try
        {
            await _huntApi!.EndAsync(_huntId);
            await Hunt_LoadState();
            _huntStatus = "Hunt ended.";
        }
        catch (Exception ex)
        {
            _huntStatus = $"End failed: {ex.Message}";
        }
        finally
        {
            _huntLoading = false;
        }
    }

    private async Task Hunt_ClaimCheckpoint(string checkpointId)
    {
        if (string.IsNullOrWhiteSpace(_huntId) || string.IsNullOrWhiteSpace(_huntStaffId))
        {
            _huntStatus = "Join a hunt first.";
            return;
        }
        Hunt_EnsureClient();
        _huntStatus = "Claiming checkpoint.";
        try
        {
            var resp = await _huntApi!.ClaimCheckpointAsync(_huntId, _huntStaffId, checkpointId);
            if (!resp.ok)
            {
                _huntStatus = resp.error ?? resp.message ?? "Claim failed.";
                return;
            }
            _huntSelectedCheckpointId = checkpointId;
            await Hunt_LoadState();
            _huntStatus = "Checkpoint claimed.";
        }
        catch (Exception ex)
        {
            _huntStatus = $"Claim failed: {ex.Message}";
        }
    }

    private async Task Hunt_CheckIn()
    {
        if (_huntState?.hunt == null || string.IsNullOrWhiteSpace(_huntId) || string.IsNullOrWhiteSpace(_huntStaffId))
        {
            _huntStatus = "Join a hunt first.";
            return;
        }

        var checkpointId = !string.IsNullOrWhiteSpace(_huntSelectedCheckpointId)
            ? _huntSelectedCheckpointId
            : _huntState.staff?.FirstOrDefault(s => s.staff_id == _huntStaffId)?.checkpoint_id;

        if (string.IsNullOrWhiteSpace(checkpointId))
        {
            _huntStatus = "Select a checkpoint first.";
            return;
        }
        if (string.IsNullOrWhiteSpace(_huntGroupCode))
        {
            _huntStatus = "Group code required.";
            return;
        }

        Hunt_EnsureClient();
        _huntStatus = "Submitting check-in.";
        try
        {
            var evidence = new
            {
                staff_name = _huntStaffName,
                territory_id = (int)Plugin.ClientState.TerritoryType,
                nearby_count = _nearbyPlayers.Length,
                nearby_players = _nearbyPlayers,
            };
            var resp = await _huntApi!.CheckInAsync(_huntId, _huntStaffId, _huntGroupCode.Trim(), checkpointId, evidence);
            if (!resp.ok)
            {
                _huntStatus = resp.error ?? "Check-in failed.";
                return;
            }
            _huntStatus = "Check-in recorded.";
            _huntGroupCode = "";
            await Hunt_LoadState();
        }
        catch (Exception ex)
        {
            _huntStatus = $"Check-in failed: {ex.Message}";
        }
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
            _bingoOwnersDirty = true;
            _bingoGameId = _bingoState.game.game_id;
            Plugin.Config.BingoLastSelectedGameId = _bingoGameId;
            Plugin.Config.Save();
            _bingoStatus = $"Loaded '{_bingoState.game.title}'.";
            Bingo_AddAction($"Loaded game {_bingoState.game.title}");
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
            if (!string.IsNullOrWhiteSpace(owner))
                _bingoCardsExpandedOwner = owner;
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
            _bingoOwnersDirty = true;
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
            Bingo_AddAction("Game started");
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
            Bingo_AddAction("Game ended");
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
            Bingo_AddAction("Stage advanced");
        }
        catch (Exception ex) { _bingoStatus = $"Advance failed: {ex.Message}"; }
        finally { _bingoLoading = false; }
    }

    private async Task Bingo_SeedPot(int amount)
    {
        if (_bingoState is null)
        {
            _bingoStatus = "Load a game first.";
            return;
        }
        if (amount <= 0)
        {
            _bingoStatus = "Seed amount must be positive.";
            return;
        }
        Bingo_EnsureClient();
        _bingoLoading = true;
        _bingoStatus = "Seeding pot.";
        try
        {
            await _bingoApi!.SeedPotAsync(_bingoState.game.game_id, amount);
            await Bingo_LoadGame(_bingoState.game.game_id);
            var currency = _bingoState.game.currency ?? "";
            _bingoStatus = $"Seeded {FormatGil(amount)} {currency}.";
            Bingo_AddAction($"Seeded {FormatGil(amount)} {currency}");
        }
        catch (Exception ex) { _bingoStatus = $"Seed failed: {ex.Message}"; }
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
            Bingo_AddAction($"Approved claim {cardId}");
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
            Bingo_AddAction($"Rejected claim {cardId}");
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
            {
                Bingo_AddAction($"Called {FormatBingoCall(last.Value)}");
                if (_bingoAnnounceCalls)
                    Plugin.ChatGui.Print($"[Forest] Called number {last.Value}.");
            }
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

    private List<string> Bingo_GetRandomAllowList(string? gameId)
    {
        if (string.IsNullOrWhiteSpace(gameId))
            return new List<string>();
        if (Plugin.Config.BingoRandomAllowListByGameId == null)
            Plugin.Config.BingoRandomAllowListByGameId = new Dictionary<string, List<string>>();
        if (!Plugin.Config.BingoRandomAllowListByGameId.TryGetValue(gameId, out var list) || list == null)
        {
            list = new List<string>();
            Plugin.Config.BingoRandomAllowListByGameId[gameId] = list;
        }
        return list;
    }

    private void Bingo_AddRandomAllow(string? gameId, string name)
    {
        if (string.IsNullOrWhiteSpace(gameId)) return;
        if (string.IsNullOrWhiteSpace(name)) return;
        var list = Bingo_GetRandomAllowList(gameId);
        if (list.Any(n => string.Equals(n, name, StringComparison.OrdinalIgnoreCase)))
            return;
        list.Add(name.Trim());
        Plugin.Config.Save();
    }

    private void Bingo_RemoveRandomAllow(string? gameId, string name)
    {
        if (string.IsNullOrWhiteSpace(gameId)) return;
        if (string.IsNullOrWhiteSpace(name)) return;
        var list = Bingo_GetRandomAllowList(gameId);
        list.RemoveAll(n => string.Equals(n, name, StringComparison.OrdinalIgnoreCase));
        Plugin.Config.Save();
    }

    private bool Bingo_IsRandomAllowedSender(string senderText, string messageText)
    {
        var gameId = _bingoState?.game.game_id ?? _bingoGameId;
        var list = Bingo_GetRandomAllowList(gameId);
        if (list.Count == 0) return false;
        foreach (var entry in list)
        {
            if (string.IsNullOrWhiteSpace(entry)) continue;
            if (!string.IsNullOrWhiteSpace(senderText) &&
                string.Equals(senderText, entry, StringComparison.OrdinalIgnoreCase))
                return true;
            if (!string.IsNullOrWhiteSpace(messageText) &&
                messageText.IndexOf(entry, StringComparison.OrdinalIgnoreCase) >= 0)
                return true;
        }
        return false;
    }

    private bool TryHandleBingoRandom(string senderText, string messageText)
    {
        if (DateTime.UtcNow < _bingoRandomCooldownUntil)
            return false;
        if (string.IsNullOrWhiteSpace(messageText)) return false;
        var lower = messageText.ToLowerInvariant();
        if (!lower.Contains("roll") && !lower.Contains("random") && !lower.Contains("lot")) return false;

        var localName = Plugin.ClientState.LocalPlayer?.Name.TextValue;
        var localLower = string.IsNullOrWhiteSpace(localName) ? "" : localName.ToLowerInvariant();
        var messageMatches =
            lower.Contains("you roll") ||
            lower.Contains("you rolled") ||
            lower.StartsWith("you ");
        var senderMatchesLocal = false;
        if (!string.IsNullOrWhiteSpace(localLower))
        {
            senderMatchesLocal = !string.IsNullOrWhiteSpace(senderText) &&
                                 string.Equals(senderText, localName, StringComparison.OrdinalIgnoreCase);
            messageMatches = messageMatches || lower.Contains(localLower);
        }
        if (!senderMatchesLocal && !messageMatches && !Bingo_IsRandomAllowedSender(senderText, messageText))
            return false;
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
            Bingo_AddAction($"Called {FormatBingoCall(rolled)}");
            if (_bingoAnnounceCalls)
                Plugin.ChatGui.Print($"[Forest] Called number {rolled}.");
            _bingoRandomCooldownUntil = DateTime.UtcNow.AddSeconds(5);
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

    private async Task Bingo_BuyForOwner(string owner, int count, bool gift)
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
            await _bingoApi!.BuyAsync(_bingoState.game.game_id, owner, count, gift);
            await Bingo_LoadOwnerCards(owner);
            await Bingo_LoadOwners();
            _bingoStatus = gift
                ? $"Gifted {count} for {owner}."
                : $"Bought {count} for {owner}.";
            Bingo_AddAction(gift ? $"Gifted {count} to {owner}" : $"Bought {count} for {owner}");

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
































