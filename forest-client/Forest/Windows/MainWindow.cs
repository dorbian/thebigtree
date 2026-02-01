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

using FFXIVClientStructs.FFXIV.Client.UI;
using FFXIVClientStructs.FFXIV.Client.System.String;

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

public partial class MainWindow : Window, IDisposable
{
    private readonly Plugin Plugin;

    // ---------- View switch ----------
    private enum View { Home, Hunt, MurderMystery, Bingo, Raffle, SpinWheel, Glam, Cardgames, Events }
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
    private const float MainSplitterPad = 6f;
    private bool _rightPaneCollapsed = false;
    private bool _pendingWindowResize = false;
    private float _pendingWindowWidth = 0f;
    private float _lastExpandedWidth = 0f;
    private float _windowExtraWidth = 0f;
    private float _lastWindowHeight = 0f;
    private const float MinWindowWidthExpanded = 900f;
    private const float MinWindowWidthCollapsed = 368f;
    private const float MinWindowHeight = 570f;
    private const float GameCardInset = 16f;
    private const float GameCardTitlePaddingLeft = 20f;
    private const float GameCardDetailsPaddingLeft = 36f;
    private const float GameCardPaddingRight = 30f;
    private const float SectionHeaderPaddingX = GameCardInset + GameCardTitlePaddingLeft + 10f;
    private DateTime _lastSessionsPoll = DateTime.MinValue;
    private bool _sessionsRefreshQueued = false;
    private bool _sessionsRefreshLoading = false;
    private bool _nearbyPlayersDirty = true;
    private bool _nearbyPlayersInitialized = false;
    private bool _nearbyPlayersAutoRefresh = false;
    private bool _nearbyPlayersScanRequested = false;
    private int _lastTerritoryId = -1;
    private string _characterKey = "global";
    private bool _characterDefaultsLoaded = false;

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
    private readonly HashSet<string> _bingoOpenOwnerCardWindows = new(StringComparer.OrdinalIgnoreCase);
    private int _bingoRandomRerollAttempts = 0;
    private List<OwnerSummary> _bingoOwners = new();
    private const int BingoRandomMax = 40;
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
    private bool _bingoWaitingForRandomRoll = false;
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
    private bool _cardgamesCreatePopupPending = false;
    private string _cardgamesCreateGameId = "";
    private bool _cardgamesOpenAfterCreate = false;
    private bool _cardgamesCreateWindowOpen = false;
    private bool _cardgamesPendingExpandAfterCreate = false;
    private readonly Dictionary<string, string> _cardgamesPlayerTokens = new();
    private readonly Dictionary<string, ISharedImmediateTexture> _cardgamesTextureCache = new();
    private readonly Dictionary<string, Task> _cardgamesTextureTasks = new();
    private readonly object _cardgamesTextureLock = new();
    private readonly HttpClient _cardgamesHttp = new();
    private bool _permissionsLoading = false;
    private bool _permissionsChecked = false;
    private string _permissionsStatus = "";
    private DateTime _permissionsLastAttempt = DateTime.MinValue;
    private readonly HashSet<string> _allowedScopes = new(StringComparer.OrdinalIgnoreCase);
    private bool _permissionsBlockedUntilKeyChange = false;
    private string _permissionsLastKey = "";
    private DateTime _iconFontLastAttempt = DateTime.MinValue;
    private bool _iconFontLoaded = false;
    private object? _iconFontObj;
    private Action? _pushIconFont;
    private Action? _popIconFont;
    private bool _rememberRightPaneState = false;
    private bool _applyInitialRightPaneState = true;

    public MainWindow(Plugin plugin)
        : base("Forest Manager##Main", ImGuiWindowFlags.NoScrollbar | ImGuiWindowFlags.NoScrollWithMouse)
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
        TryInitIconFont();
        _rememberRightPaneState = Plugin.Config.RightPaneRemembered;
        _rightPaneCollapsed = true;
        _permissionsLastKey = Plugin.Config.BingoApiKey ?? "";
        _activeEventCode = Plugin.Config.LastEventCode ?? "";

            // Load venue on startup if connected
            if (Plugin.Config.BingoConnected && Plugin.VenuesApi != null)
            {
                _ = Venue_LoadCurrent();
            }

        SizeConstraints = new WindowSizeConstraints
        {
            MinimumSize = new Vector2(MinWindowWidthExpanded, MinWindowHeight),
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
            _bingoGames = list?.Where(g => g.active).ToList() ?? new();
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
            && _bingoApi is not null
            && !string.IsNullOrWhiteSpace(_bingoGameId)
            && _bingoState is not null
            && _bingoState.game.started
            && _bingoState.game.active
            && Plugin.Config.BingoConnected;
        if (allowManualRoll)
            _ = TryHandleBingoRandomAsync(sender.TextValue, message.TextValue);

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

        if (!_characterDefaultsLoaded)
        {
            _characterKey = Plugin.ClientState.LocalPlayer?.Name.TextValue ?? "global";
            LoadCharacterDefaults();
            _characterDefaultsLoaded = true;
        }

        CheckVotingPeriod();
        CheckCountdownCompletion();

        if ((DateTime.UtcNow - _lastRefreshTime).TotalSeconds < 10) return;
        _lastRefreshTime = DateTime.UtcNow;

        Raffle_CheckAutoClose();
        if (!Plugin.Config.DisableNearbyScan)
        {
            int territoryId = (int)Plugin.ClientState.TerritoryType;
            if (_lastTerritoryId != territoryId)
            {
                _lastTerritoryId = territoryId;
                _nearbyPlayersDirty = true;
                _nearbyPlayersAutoRefresh = true;
            }
        }

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

        if ((DateTime.UtcNow - _lastSessionsPoll).TotalSeconds >= 60)
            RequestSessionsRefresh(false);
        if (_sessionsRefreshQueued && (DateTime.UtcNow - _lastSessionsPoll).TotalSeconds >= 10)
        {
            _sessionsRefreshQueued = false;
            RequestSessionsRefresh(false);
        }
    }

    private void UpdateTrackedPlayers()
    {
        var tracked = BuildTrackedPlayerSet();
        bool filterToRoster = tracked.Count > 0;
        _nearbyPlayers = Plugin.ObjectTable
            .Where(o => o is IPlayerCharacter pc
                && (!filterToRoster || tracked.Contains(pc.Name.TextValue)))
            .Cast<IPlayerCharacter>()
            .Select(pc => pc.Name.TextValue)
            .Distinct()
            .OrderBy(n => n)
            .ToArray();
    }

    private void EnsureNearbyPlayersLoaded()
    {
        if (Plugin.Config.DisableNearbyScan)
        {
            _nearbyPlayers = Array.Empty<string>();
            _nearbyPlayersInitialized = true;
            _nearbyPlayersDirty = false;
            return;
        }
        if (!_nearbyPlayersScanRequested && !_nearbyPlayersAutoRefresh)
            return;
        if (!_nearbyPlayersDirty && _nearbyPlayersInitialized)
            return;
        UpdateTrackedPlayers();
        _nearbyPlayersInitialized = true;
        _nearbyPlayersDirty = false;
        _nearbyPlayersScanRequested = false;
        _nearbyPlayersAutoRefresh = false;
    }

    private HashSet<string> BuildTrackedPlayerSet()
    {
        var tracked = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        if (_selectedSession is null && _view != View.MurderMystery)
            return tracked;

        switch (_selectedSession?.TargetView ?? _view)
        {
            case View.MurderMystery:
            {
                var game = Plugin.Config.CurrentGame;
                if (game == null)
                    return tracked;
                if (!string.IsNullOrWhiteSpace(game.Killer))
                    tracked.Add(game.Killer);
                if (game.ActivePlayers != null)
                    foreach (var name in game.ActivePlayers)
                        tracked.Add(name);
                if (game.DeadPlayers != null)
                    foreach (var name in game.DeadPlayers)
                        tracked.Add(name);
                if (game.ImprisonedPlayers != null)
                    foreach (var name in game.ImprisonedPlayers)
                        tracked.Add(name);
                break;
            }
        }

        return tracked;
    }

    // ========================= DRAW =========================
    public override void Draw()
    {
        if (!_iconFontLoaded)
            TryInitIconFont();
        float delta = ImGui.GetIO().DeltaTime;
        float target = _controlSurfaceOpen ? 1f : 0f;
        float step = Math.Clamp(delta * 8f, 0f, 1f);
        _controlSurfaceAnim = Math.Clamp(_controlSurfaceAnim + (target - _controlSurfaceAnim) * step, 0f, 1f);
        var windowSize = ImGui.GetWindowSize();
        _lastWindowHeight = Math.Max(windowSize.Y, MinWindowHeight);
        if (windowSize.Y < MinWindowHeight)
            ImGui.SetWindowSize(new Vector2(windowSize.X, MinWindowHeight), ImGuiCond.Always);
        if (_applyInitialRightPaneState)
        {
            _applyInitialRightPaneState = false;
            if (_rightPaneCollapsed)
                SetRightPaneCollapsed(true, true);
        }
        if (_pendingWindowResize)
        {
            ImGui.SetWindowSize(new Vector2(_pendingWindowWidth, _lastWindowHeight), ImGuiCond.Always);
            _pendingWindowResize = false;
            _pendingWindowWidth = 0f;
        }
        if (_cardgamesPendingExpandAfterCreate)
        {
            _cardgamesPendingExpandAfterCreate = false;
            SetRightPaneCollapsed(false, true);
        }

        var avail = ImGui.GetContentRegionAvail();
        float minRight = 260f;
        float minLeft = 240f;
        float splitTotal = VerticalSplitterThickness + MainSplitterPad * 2f;
        if (_rightPaneCollapsed)
        {
            _leftPaneWidth = Math.Max(minLeft, avail.X);
        }
        else
        {
            float maxLeft = Math.Max(minLeft, avail.X - minRight - splitTotal);
            _leftPaneWidth = Math.Clamp(_leftPaneWidth, minLeft, maxLeft);
        }

        ImGui.PushStyleVar(ImGuiStyleVar.WindowPadding, new Vector2(8f, 8f));
        ImGui.BeginChild("LeftPaneWrap", new Vector2(_leftPaneWidth, 0), false, ImGuiWindowFlags.NoScrollbar | ImGuiWindowFlags.NoScrollWithMouse);
        DrawLeftPane();
        ImGui.EndChild();
        ImGui.PopStyleVar();

        if (!_rightPaneCollapsed)
        {
            ImGui.SameLine(0, 0);
            ImGui.Dummy(new Vector2(MainSplitterPad, avail.Y));
            ImGui.SameLine(0, 0);
            ImGui.Button("##SplitMain", new Vector2(VerticalSplitterThickness, avail.Y));
            if (ImGui.IsItemActive() && ImGui.IsMouseDragging(0))
            {
                float dragDelta = ImGui.GetIO().MouseDelta.X;
                _leftPaneWidth = Math.Clamp(_leftPaneWidth + dragDelta, minLeft, avail.X - minRight - splitTotal);
            }
            ImGui.SameLine(0, 0);
            ImGui.Dummy(new Vector2(MainSplitterPad, avail.Y));
            ImGui.SameLine(0, 0);
            ImGui.PushStyleVar(ImGuiStyleVar.WindowPadding, new Vector2(10f, 10f));
            ImGui.BeginChild("RightPane", Vector2.Zero, false, 0);
            switch (_topView)
            {
                case TopView.Games: DrawGamesView(); break;
                case TopView.Players: DrawPlayersView(); break;
                case TopView.Sessions: DrawSessionsControlSurface(); break;
            }
              ImGui.EndChild();
              ImGui.PopStyleVar();
        }

        DrawCardgamesCreateWindow();
    }

    // ========================= LEFT PANE =========================
    private void DrawLeftPane()
    {
        float totalH = ImGui.GetContentRegionAvail().Y;
        float topH = Math.Max(SplitterMinTop, totalH * _leftSplitRatio - SplitterThickness * 0.5f);
        float bottomH = Math.Max(SplitterMinBottom, totalH - topH - SplitterThickness);

        ImGui.PushStyleVar(ImGuiStyleVar.WindowPadding, new Vector2(8f, 8f));
        ImGui.BeginChild("PlayersTop", new Vector2(0, topH), true, 0);
        DrawPlayersList();
        ImGui.EndChild();
        ImGui.PopStyleVar();

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

        ImGui.PushStyleVar(ImGuiStyleVar.WindowPadding, new Vector2(8f, 8f));
        float footerH = Math.Max(44f, ImGui.GetTextLineHeightWithSpacing() + 16f);
        float sessionsH = Math.Max(0f, bottomH - footerH);
        ImGui.BeginChild("SessionsArea", new Vector2(0, sessionsH), true, ImGuiWindowFlags.NoScrollbar | ImGuiWindowFlags.NoScrollWithMouse);
        DrawSessionsList();
        ImGui.EndChild();
        ImGui.PushStyleVar(ImGuiStyleVar.WindowPadding, new Vector2(8f, 6f));
        ImGui.BeginChild("SessionsStatusFooter", new Vector2(0, footerH), true, ImGuiWindowFlags.NoScrollbar | ImGuiWindowFlags.NoScrollWithMouse);
        DrawPermissionsStatusFooter();
        ImGui.EndChild();
        ImGui.PopStyleVar();
        ImGui.PopStyleVar();
    }

    // --- Player list: full-width hit area; right-click opens context ---
    private void DrawPlayersList()
    {
        ImGui.TextDisabled("Players (nearby)");
        ImGui.SameLine();
        if (SmallAccentIconButton("\uf021", "Scan", "players-scan"))
        {
            if (!Plugin.Config.DisableNearbyScan)
            {
                _nearbyPlayersDirty = true;
                _nearbyPlayersScanRequested = true;
                EnsureNearbyPlayersLoaded();
            }
        }
        ImGui.Separator();
        ImGui.Spacing();

        float rowH = ImGui.GetTextLineHeightWithSpacing();
        float padX = 6f;

        EnsureNearbyPlayersLoaded();
        if (_nearbyPlayers.Length == 0)
        {
            ImGui.TextDisabled(Plugin.Config.DisableNearbyScan
                ? "Nearby scan disabled."
                : _nearbyPlayersInitialized ? "No players nearby." : "Press Scan to load nearby players.");
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

        ImGui.Dummy(new Vector2(0, 8f));
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
    private void DrawBingoGamesList()
    {
        ImGui.TextDisabled("Bingo Games");
        ImGui.SameLine();
        if (ImGui.SmallButton("Refresh"))
            _ = Bingo_LoadGames();

        if (string.IsNullOrWhiteSpace(Plugin.Config.BingoApiKey))
        {
            ImGui.TextDisabled("Not connected to bingo server.");
            return;
        }

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
	        // Wrap Bingo admin in a proper "card" container (background + rounding) to match cardgames.
	        var avail = ImGui.GetContentRegionAvail();
	        var accent = new Vector4(0.25f, 0.90f, 0.45f, 1.0f); // Bingo green
	        var style = ImGui.GetStyle();
	        float rounding = 12f;
	        var pad = new Vector2(14f, 12f);

	        // Child with padding; we draw the card background ourselves so it always exists (user request).
	        ImGui.PushStyleVar(ImGuiStyleVar.ChildRounding, rounding);
	        ImGui.PushStyleVar(ImGuiStyleVar.WindowPadding, pad);
	        ImGui.BeginChild("BingoAdminCard", new Vector2(avail.X, avail.Y), false, 0);
	        {
	            // Background (tinted accent) + border
	            var dl = ImGui.GetWindowDrawList();
	            var p0 = ImGui.GetWindowPos();
	            var p1 = p0 + ImGui.GetWindowSize();
	            uint bg = ImGui.ColorConvertFloat4ToU32(new Vector4(accent.X * 0.10f, accent.Y * 0.10f, accent.Z * 0.10f, 0.95f));
	            uint border = ImGui.ColorConvertFloat4ToU32(new Vector4(accent.X, accent.Y, accent.Z, 0.55f));
	            dl.AddRectFilled(p0, p1, bg, rounding);
	            dl.AddRect(p0, p1, border, rounding, 0, 1.0f);

	            DrawBingoAdminPanelContent();
	        }
	        ImGui.EndChild();
	        ImGui.PopStyleVar(2);
    }

    private void DrawBingoAdminPanelContent()
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

        // Settings tab removed: clamp any legacy saved index
        if (_bingoUiTabIndex == 5)
        {
            _bingoUiTabIndex = 0;
            Plugin.Config.BingoUiTabIndex = 0;
            Plugin.Config.Save();
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
		            if (DrawBingoHeaderBlock(game, uiState))
		            {
		                if (Math.Abs(scale - 1f) > 0.01f)
		                    ImGui.SetWindowFontScale(1f);
		                return;
		            }
		        }

        if (uiState == BingoUiState.Running && !_bingoLoading && !ImGui.GetIO().WantTextInput)
        {
            if (ImGui.IsKeyPressed(Dalamud.Bindings.ImGui.ImGuiKey.N))
            {
                Bingo_Roll();
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
if (BeginBingoTab("History", 4))
            {
                DrawBingoPrimaryActionRow(uiState, game);
                DrawBingoHistoryTab(game);
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
            _ => "Roll"
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
            BingoUiState.NoGameLoaded => "Select a game from the list on the left.",
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
                        Bingo_Roll();
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

            bool canCall = hasGame && game!.active && game!.started;
            using (var dis = ImRaii.Disabled(!canCall || _bingoLoading))
            {
                if (ImGui.MenuItem("Roll"))
                    Bingo_Roll();
            }
            if (!canCall || _bingoLoading)
                DrawDisabledTooltip("Game must be active and started.");

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

		    
private bool DrawBingoHeaderBlock(GameInfo game, BingoUiState uiState)
        {
            // Compact header: only connection/status + stage/pot + last call + payouts.
            var accent = new Vector4(0.25f, 0.90f, 0.45f, 1.0f);
            var style = ImGui.GetStyle();
            float spacing = style.ItemSpacing.X;

            // Back arrow (collapses the control surface) — match the card background (no orange/red button)
            bool back = SmallIconButton("\uf053", "<", "bingo-back", matchPanelBg: true);
            if (ImGui.IsItemHovered())
                ImGui.SetTooltip("Back");
            if (back)
            {
                // Collapse right panel (keeps the list visible)
                SetRightPaneCollapsed(true);
                return true;
            }

            // Shared box styling (bright green like the old "Last Call" field)
            float lineH = ImGui.GetTextLineHeight();
            float boxPadX = 10f;
            float boxPadY = 8f;
            float rounding = 10f;

            uint bg = ImGui.ColorConvertFloat4ToU32(new Vector4(0.45f, 0.95f, 0.70f, 0.95f));
            uint border = ImGui.ColorConvertFloat4ToU32(new Vector4(0.22f, 0.70f, 0.38f, 0.92f));

            void DrawInfoBox(string id, string l1, string? l2 = null)
            {
                var dl = ImGui.GetWindowDrawList();
                float w = ImGui.CalcTextSize(l1).X;
                if (!string.IsNullOrWhiteSpace(l2))
                    w = Math.Max(w, ImGui.CalcTextSize(l2).X);
                w = Math.Max(80f, w + boxPadX * 2f);

                float h = lineH + boxPadY * 2f;
                if (!string.IsNullOrWhiteSpace(l2))
                    h = lineH * 2f + boxPadY * 2f;

                var p0 = ImGui.GetCursorScreenPos();
                var p1 = p0 + new Vector2(w, h);
                dl.AddRectFilled(p0, p1, bg, rounding);
                dl.AddRect(p0, p1, border, rounding, 0, 1.0f);

                ImGui.SetCursorPos(ImGui.GetCursorPos() + new Vector2(boxPadX, boxPadY));
                ImGui.TextUnformatted(l1);
                if (!string.IsNullOrWhiteSpace(l2))
                    ImGui.TextUnformatted(l2);

                // restore cursor for next item
                ImGui.SetCursorPos(new Vector2(ImGui.GetCursorPosX() - boxPadX, ImGui.GetCursorPosY() - boxPadY));
                ImGui.SameLine();
                ImGui.Dummy(new Vector2(w + spacing, h)); // reserve space
                ImGui.SameLine();
            }

            // First row: connection + status (compact)
            ImGui.SameLine();
            string serverText = "Server: connected";
            string statusText = uiState switch
            {
                BingoUiState.NoGameLoaded => "Status: No game",
                BingoUiState.Ready => "Status: Ready",
                BingoUiState.Running => "Status: Live",
                BingoUiState.StageComplete => "Status: Stage complete",
                _ => "Status: Finished"
            };

            // Draw server/status boxes manually (so we can control spacing precisely)
            var dlTop = ImGui.GetWindowDrawList();
            float topStartX = ImGui.GetCursorPosX();
            float topStartY = ImGui.GetCursorPosY();
            ImGui.SetCursorPos(new Vector2(topStartX, topStartY));

            float serverW = Math.Max(140f, ImGui.CalcTextSize(serverText).X + boxPadX * 2f);
            float statusW = Math.Max(140f, ImGui.CalcTextSize(statusText).X + boxPadX * 2f);
            float topH = lineH + boxPadY * 2f;

            // Server box
            {
                var p0 = ImGui.GetCursorScreenPos();
                var p1 = p0 + new Vector2(serverW, topH);
                dlTop.AddRectFilled(p0, p1, bg, rounding);
                dlTop.AddRect(p0, p1, border, rounding, 0, 1.0f);
                ImGui.SetCursorPos(new Vector2(topStartX + boxPadX, topStartY + boxPadY));
                ImGui.TextUnformatted(serverText);
                ImGui.SetCursorPos(new Vector2(topStartX + serverW + spacing, topStartY));
            }

            // Status box
            float statusX = topStartX + serverW + spacing;
            {
                ImGui.SetCursorPos(new Vector2(statusX, topStartY));
                var p0 = ImGui.GetCursorScreenPos();
                var p1 = p0 + new Vector2(statusW, topH);
                dlTop.AddRectFilled(p0, p1, bg, rounding);
                dlTop.AddRect(p0, p1, border, rounding, 0, 1.0f);
                ImGui.SetCursorPos(new Vector2(statusX + boxPadX, topStartY + boxPadY));
                ImGui.TextUnformatted(statusText);
            }

            // Move cursor below row 1
            ImGui.SetCursorPos(new Vector2(topStartX, topStartY + topH + style.ItemSpacing.Y));
            ImGui.Spacing();

            // Second row: stage/pot box (left), last box (middle), payouts box (right)
            string stage1 = $"Stage: {game.stage}";
            string stage2 = $"Pot: {FormatGil(game.pot)} {game.currency}";
            float stageW = Math.Max(ImGui.CalcTextSize(stage1).X, ImGui.CalcTextSize(stage2).X) + boxPadX * 2f;
            stageW = Math.Max(160f, stageW);
            float stageH = lineH * 2f + boxPadY * 2f;

            float rowY = ImGui.GetCursorPosY();
            float leftX = ImGui.GetCursorPosX();

            // Stage box
            {
                var p0 = ImGui.GetCursorScreenPos();
                var p1 = p0 + new Vector2(stageW, stageH);
                var dl = ImGui.GetWindowDrawList();
                dl.AddRectFilled(p0, p1, bg, rounding);
                dl.AddRect(p0, p1, border, rounding, 0, 1.0f);
                ImGui.SetCursorPos(new Vector2(leftX + boxPadX, rowY + boxPadY));
                ImGui.TextUnformatted(stage1);
                ImGui.TextUnformatted(stage2);
            }

            // Payouts box (right)
            float payoutsH = lineH * 3f + boxPadY * 2f;
            float payoutsW = Math.Max(200f, ImGui.CalcTextSize("Full: 999,999,999").X + boxPadX * 2f);
            float right = ImGui.GetWindowContentRegionMax().X;
            float payoutsX = right - payoutsW;

            // Last box (to the left of payouts)
            int? lastCalled = game.last_called;
            if ((!lastCalled.HasValue || lastCalled.Value == 0) && game.called is { Length: > 0 })
                lastCalled = game.called[^1];
            var lastLabel = lastCalled.HasValue ? FormatBingoCall(lastCalled.Value) : "--";
            var count = game.called?.Length ?? 0;

            string last1 = $"Last: {lastLabel}";
            string last2 = $"Called: {count}";
            float lastW = Math.Max(ImGui.CalcTextSize(last1).X, ImGui.CalcTextSize(last2).X) + boxPadX * 2f;
            lastW = Math.Max(120f, lastW);
            float lastH = lineH * 2f + boxPadY * 2f;

            float minLastX = leftX + stageW + spacing;
            float lastX = payoutsX - spacing - lastW;
            if (lastX < minLastX)
            {
                lastX = minLastX;
                float maxLastW = Math.Max(80f, payoutsX - spacing - lastX);
                if (lastW > maxLastW)
                    lastW = maxLastW;
            }

            {
                ImGui.SetCursorPos(new Vector2(lastX, rowY));
                var p0 = ImGui.GetCursorScreenPos();
                var p1 = p0 + new Vector2(lastW, lastH);
                var dl = ImGui.GetWindowDrawList();
                dl.AddRectFilled(p0, p1, bg, rounding);
                dl.AddRect(p0, p1, border, rounding, 0, 1.0f);
                ImGui.SetCursorPos(new Vector2(lastX + boxPadX, rowY + boxPadY));
                ImGui.TextUnformatted(last1);
                ImGui.TextUnformatted(last2);
            }

                        // (layout) payouts are anchored right; last box is anchored to payouts.

            {
                ImGui.SetCursorPos(new Vector2(payoutsX, rowY));
                var p0 = ImGui.GetCursorScreenPos();
                var p1 = p0 + new Vector2(payoutsW, payoutsH);
                var dl = ImGui.GetWindowDrawList();
                dl.AddRectFilled(p0, p1, bg, rounding);
                dl.AddRect(p0, p1, border, rounding, 0, 1.0f);

                ImGui.SetCursorPos(new Vector2(payoutsX + boxPadX, rowY + boxPadY));
                if (game.payouts != null)
                {
                    ImGui.TextUnformatted($"Single: {FormatGil(game.payouts.single)}");
                    ImGui.TextUnformatted($"Double: {FormatGil(game.payouts.@double)}");
                    ImGui.TextUnformatted($"Full:   {FormatGil(game.payouts.full)}");
                }
                else
                {
                    ImGui.TextDisabled("Single: -");
                    ImGui.TextDisabled("Double: -");
                    ImGui.TextDisabled("Full:   -");
                }
            }

            // Move cursor below header block cleanly.
            float headerBottom = rowY + Math.Max(stageH, Math.Max(lastH, payoutsH)) + style.ItemSpacing.Y;
            ImGui.SetCursorPosY(headerBottom);
            ImGui.Separator();
            ImGui.Spacing();
            return false;
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
                Plugin.Framework.RunOnFrameworkThread(() => Plugin.ChatGui.Print($"[Bingo] Call {label}"));
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

	        // Game summary is already surfaced in the Bingo header block.
	        // Keep this tab focused on actions and advanced/admin tooling.

        ImGui.TextUnformatted("Last Action");
        ImGui.TextDisabled(string.IsNullOrWhiteSpace(_bingoLastAction) ? "-" : _bingoLastAction);

                // Advanced (always visible)
        ImGui.Spacing();
        ImGui.TextUnformatted("Advanced");
        ImGui.Separator();
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


        if (!_bingoCompactMode)
        {
            ImGui.Spacing();
            ImGui.TextUnformatted("Admin Tools");
            ImGui.Separator();
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

        // Build a per-owner summary of bingo claims so the Players list can show:
        // - whether someone has bingo (from in-game chat/admin claim or from the website button)
        // - the highest stage they have (Single/Double/Full) only once, even if multiple claims exist
        // Note: public(web) claims may be pending/denied; admin(chat) claims are implicit approvals.
        var bestClaimByOwner = new Dictionary<string, Claim>(StringComparer.OrdinalIgnoreCase);
        var claimsAll = game.claims;
        if (claimsAll != null)
        {
            for (int ci = 0; ci < claimsAll.Length; ci++)
            {
                var c = claimsAll[ci];
                var name = (c.owner_name ?? "").Trim();
                if (string.IsNullOrWhiteSpace(name))
                    continue;

                // Ignore denied claims for "has bingo" purposes.
                // If the only thing we have is denied, we still keep the "best" denied claim as a hint.
                int rank = BingoStageRank(c.stage);
                if (rank < 0)
                    continue;

                if (!bestClaimByOwner.TryGetValue(name, out var current))
                {
                    bestClaimByOwner[name] = c;
                    continue;
                }

                // Prefer non-denied over denied
                bool curDenied = current.denied;
                bool newDenied = c.denied;
                if (curDenied && !newDenied)
                {
                    bestClaimByOwner[name] = c;
                    continue;
                }
                if (!curDenied && newDenied)
                    continue;

                // Prefer higher stage (Full > Double > Single)
                int curRank = BingoStageRank(current.stage);
                if (rank > curRank)
                {
                    bestClaimByOwner[name] = c;
                    continue;
                }
                if (rank < curRank)
                    continue;

                // Same stage: prefer approved over pending, then newest timestamp
                bool curPending = current.pending;
                bool newPending = c.pending;
                if (curPending && !newPending)
                {
                    bestClaimByOwner[name] = c;
                    continue;
                }
                if (!curPending && newPending)
                    continue;

                long curTs = current.ts ?? 0;
                long newTs = c.ts ?? 0;
                if (newTs > curTs)
                    bestClaimByOwner[name] = c;
            }
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
                ImGui.TableSetupColumn("Status", ImGuiTableColumnFlags.WidthFixed, 140f);
                ImGui.TableSetupColumn("Actions", ImGuiTableColumnFlags.WidthFixed, 78f);
                ImGui.TableHeadersRow();

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
                        bestClaimByOwner.TryGetValue(owner.owner_name, out var best);
                        ImGui.TextUnformatted(FormatBingoOwnerStatus(best));
                        ImGui.TableNextColumn();

                        // Actions: [Copy URL] [View cards]
                        string ownerUrl = BuildBingoOwnerUrl(game, owner);
                        bool canCopy = !string.IsNullOrWhiteSpace(ownerUrl);
                        using (var dis = ImRaii.Disabled(!canCopy))
                        {
                            if (SquareIconButton("\uf0c5", "Copy", $"bingo-owner-url-{i}"))
                            {
                                if (canCopy)
                                    ImGui.SetClipboardText(ownerUrl);
                            }
                        }
                        if (ImGui.IsItemHovered())
                        {
                            ImGui.BeginTooltip();
                            ImGui.TextUnformatted(canCopy ? "Copy player URL" : "No URL available");
                            if (canCopy)
                                ImGui.TextDisabled(ownerUrl);
                            ImGui.EndTooltip();
                        }
                        ImGui.SameLine();

                        if (SquareIconButton("\uf06e", "View", $"bingo-owner-view-{i}"))
                        {
                            if (!string.IsNullOrWhiteSpace(owner.owner_name))
                            {
                                _ = Bingo_LoadOwnerCards(owner.owner_name);
                                _bingoOpenOwnerCardWindows.Add(owner.owner_name);
                            }
                        }
                        if (ImGui.IsItemHovered())
                        {
                            ImGui.BeginTooltip();
                            ImGui.TextUnformatted("View cards");
                            ImGui.EndTooltip();
                        }
                    }
                }
                ImGui.EndTable();

            // --- Owner card pop-up windows (can have multiple open) ---
            foreach (var ownerName in _bingoOpenOwnerCardWindows.ToArray())
            {
                if (string.IsNullOrWhiteSpace(ownerName))
                    continue;

                bool open = true;
                var windowTitle = $"Bingo Cards - {ownerName}##bingo-cards-{ownerName}";
                if (ImGui.Begin(windowTitle, ref open, ImGuiWindowFlags.AlwaysAutoResize))
                {
                    if (!_bingoOwnerCards.TryGetValue(ownerName, out var cards) || cards.Count == 0)
                    {
                        ImGui.TextDisabled("No cards loaded.");
                        if (ImGui.Button("Refresh"))
                            _ = Bingo_LoadOwnerCards(ownerName);
                    }
                    else
                    {
                        ImGui.TextUnformatted($"{cards.Count} card(s)");
                        ImGui.SameLine();
                        if (ImGui.SmallButton("Refresh"))
                            _ = Bingo_LoadOwnerCards(ownerName);

                        ImGui.Separator();
                        for (int ci = 0; ci < cards.Count; ci++)
                        {
                            var card = cards[ci];
                            ImGui.PushID(ci);
                            ImGui.TextUnformatted($"Card {ci + 1}");
                            // draw the existing card renderer
                            Bingo_DrawCard(card, _bingoState?.game?.called ?? Array.Empty<int>());
                            ImGui.Separator();
                            ImGui.PopID();
                        }
                    }
                }
                ImGui.End();

                if (!open)
                    _bingoOpenOwnerCardWindows.Remove(ownerName);
            }

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

    private static int BingoStageRank(string? stage)
    {
        if (string.IsNullOrWhiteSpace(stage))
            return -1;
        return stage.Trim().ToLowerInvariant() switch
        {
            "single" => 0,
            "double" => 1,
            "full" => 2,
            _ => -1,
        };
    }

    private static string FormatBingoStageLabel(string? stage)
    {
        if (string.IsNullOrWhiteSpace(stage))
            return "Bingo";
        return stage.Trim().ToLowerInvariant() switch
        {
            "single" => "Single",
            "double" => "Double",
            "full" => "Full",
            _ => "Bingo",
        };
    }

    private static string FormatBingoSourceLabel(string? source)
    {
        var s = (source ?? "").Trim().ToLowerInvariant();
        return s switch
        {
            "public" => "Web",
            "admin" => "Chat",
            _ => string.IsNullOrWhiteSpace(s) ? "Chat" : s,
        };
    }

    private static string FormatBingoOwnerStatus(Claim? best)
    {
        if (best == null)
            return "-";

        string stage = FormatBingoStageLabel(best.stage);
        string src = FormatBingoSourceLabel(best.source);

        // Denied claims don't mean the player "has bingo", but it is still useful to surface.
        if (best.denied)
            return $"{stage} ({src}, denied)";
        if (best.pending)
            return $"{stage} ({src}, pending)";
        return $"{stage} ({src})";
    }

    private string BuildBingoOwnerUrl(GameInfo game, OwnerSummary owner)
    {
        try
        {
            var baseUrl = (Plugin.Config.BingoApiBaseUrl ?? "https://rites.thebigtree.life").Trim();
            if (string.IsNullOrWhiteSpace(baseUrl))
                return string.Empty;
            baseUrl = baseUrl.TrimEnd('/');

            // Prefer token-based URLs when available (short + stable).
            if (!string.IsNullOrWhiteSpace(owner.token))
            {
                var token = Uri.EscapeDataString(owner.token);
                return $"{baseUrl}/bingo/owner?token={token}";
            }

            // Fallback to game+owner query.
            var gid = Uri.EscapeDataString(game.game_id ?? "");
            var name = Uri.EscapeDataString(owner.owner_name ?? "");
            if (string.IsNullOrWhiteSpace(gid) || string.IsNullOrWhiteSpace(name))
                return string.Empty;
            return $"{baseUrl}/bingo/owner?game={gid}&owner={name}";
        }
        catch
        {
            return string.Empty;
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
        public bool CanClose { get; set; } = false;
        public string TypeIcon { get; set; } = "-";
    }

    private static string StatusIcon(string status)
    {
        var val = (status ?? "").ToLowerInvariant();
        return val switch
        {
            "live" => "\uf058",
            "waiting" => "\uf111",
            "ready" => "\uf111",
            "created" => "\uf111",
            "draft" => "\uf111",
            "finished" => "\uf057",
            _ => "\uf111",
        };
    }

    private static string ModeIcon(bool managed) => managed ? "\uf1eb" : "\uf6ac";

    private static string TypeIcon(SessionCategory category)
    {
        return category switch
        {
            SessionCategory.Casino => "\uf51e",
            SessionCategory.Draw => "\uf06b",
            SessionCategory.Party => "\uf0c0",
            _ => "\uf111",
        };
    }

    private static string StatusFallback(string status)
    {
        var val = (status ?? "").ToLowerInvariant();
        return val switch
        {
            "live" => "L",
            "waiting" => "W",
            "ready" => "W",
            "created" => "W",
            "draft" => "W",
            "finished" => "F",
            _ => "-",
        };
    }

    private static string ModeFallback(bool managed) => managed ? "M" : "L";
    private static string TypeFallback(SessionCategory category)
        => category switch { SessionCategory.Casino => "C", SessionCategory.Draw => "D", SessionCategory.Party => "P", _ => "-" };
    private void RequestSessionsRefresh(bool userAction)
    {
        if (_sessionsRefreshLoading)
            return;
        if ((DateTime.UtcNow - _lastSessionsPoll).TotalSeconds < 10)
        {
            if (userAction)
                _sessionsRefreshQueued = true;
            return;
        }
        _sessionsRefreshQueued = false;
        _ = RefreshSessionsAsync();
    }

    private async Task RefreshSessionsAsync()
    {
        if (_sessionsRefreshLoading)
            return;
        _sessionsRefreshLoading = true;
        _lastSessionsPoll = DateTime.UtcNow;
        try
        {
            if (!_permissionsChecked && !_permissionsLoading)
                await Permissions_Load();
            if (CanLoadCardgames()) _ = Cardgames_LoadSessions();
            if (CanLoadBingo()) _ = Bingo_LoadGames();
            if (CanLoadHunt()) _ = Hunt_LoadList();
        }
        finally
        {
            _sessionsRefreshLoading = false;
        }
    }

    private static Vector4 StatusColor(string status)
    {
        var val = (status ?? "").ToLowerInvariant();
        return val switch
        {
            "live" => new Vector4(0.35f, 0.85f, 0.45f, 1.0f),
            "waiting" => new Vector4(0.95f, 0.75f, 0.25f, 1.0f),
            "ready" => new Vector4(0.95f, 0.75f, 0.25f, 1.0f),
            "created" => new Vector4(0.95f, 0.75f, 0.25f, 1.0f),
            "draft" => new Vector4(0.95f, 0.75f, 0.25f, 1.0f),
            "finished" => new Vector4(0.70f, 0.70f, 0.70f, 1.0f),
            _ => new Vector4(0.70f, 0.70f, 0.70f, 1.0f),
        };
    }

    private static Vector4 ModeColor(bool managed)
    {
        return managed
            ? new Vector4(0.40f, 0.80f, 0.95f, 1.0f)
            : new Vector4(0.65f, 0.65f, 0.65f, 1.0f);
    }

    private void DrawCenteredText(string text, Vector4 color)
    {
        float avail = ImGui.GetContentRegionAvail().X;
        float textWidth = ImGui.CalcTextSize(text).X;
        float offset = Math.Max(0f, (avail - textWidth) * 0.5f);
        ImGui.SetCursorPosX(ImGui.GetCursorPosX() + offset);
        ImGui.TextColored(color, text);
    }

    private bool CenteredSmallButton(string label, string id, Vector4 color, bool matchPanelBg = true)
    {
        var style = ImGui.GetStyle();
        int styleCount = 0;
        if (matchPanelBg)
        {
            var baseColor = style.Colors[(int)ImGuiCol.ChildBg];
            ImGui.PushStyleColor(ImGuiCol.Button, baseColor);
            ImGui.PushStyleColor(ImGuiCol.ButtonHovered, Tint(baseColor, 0.04f));
            ImGui.PushStyleColor(ImGuiCol.ButtonActive, Tint(baseColor, -0.04f));
            styleCount = 3;
        }
        float avail = ImGui.GetContentRegionAvail().X;
        float textWidth = ImGui.CalcTextSize(label).X;
        float btnWidth = textWidth + style.FramePadding.X * 2f;
        float offset = Math.Max(0f, (avail - btnWidth) * 0.5f);
        ImGui.SetCursorPosX(ImGui.GetCursorPosX() + offset);
        ImGui.PushStyleColor(ImGuiCol.Text, ImGui.ColorConvertFloat4ToU32(color));
        bool clicked = ImGui.SmallButton($"{label}##{id}");
        ImGui.PopStyleColor();
        if (styleCount > 0)
            ImGui.PopStyleColor(styleCount);
        return clicked;
    }

    private void TryInitIconFont()
    {
        if (_iconFontLoaded)
            return;
        if ((DateTime.UtcNow - _iconFontLastAttempt).TotalSeconds < 2)
            return;
        _iconFontLastAttempt = DateTime.UtcNow;
        try
        {
            var uiBuilder = Plugin.PluginInterface.UiBuilder;
            var prop = uiBuilder.GetType().GetProperty("IconFont");
            if (prop == null)
                return;
            var value = prop.GetValue(uiBuilder);
            if (value is ImFontPtr bindingFont)
            {
                _iconFontObj = bindingFont;
                _pushIconFont = () => ImGui.PushFont(bindingFont);
                _popIconFont = () => ImGui.PopFont();
                _iconFontLoaded = true;
                return;
            }
            if (value is ImGuiNET.ImFontPtr netFont)
            {
                _iconFontObj = netFont;
                _pushIconFont = () => ImGuiNET.ImGui.PushFont(netFont);
                _popIconFont = () => ImGuiNET.ImGui.PopFont();
                _iconFontLoaded = true;
                return;
            }
        }
        catch
        {
            _iconFontLoaded = false;
        }
    }

    private void DrawCenteredIconText(string icon, string fallback, Vector4 color)
    {
        if (_iconFontLoaded)
        {
            _pushIconFont?.Invoke();
            DrawCenteredText(icon, color);
            _popIconFont?.Invoke();
        }
        else
        {
            DrawCenteredText(fallback, color);
        }
    }

    private bool CenteredIconButton(string icon, string fallback, string id, Vector4 color, bool matchPanelBg = true)
    {
        if (_iconFontLoaded)
        {
            _pushIconFont?.Invoke();
            bool clicked = CenteredSmallButton(icon, id, color, matchPanelBg);
            _popIconFont?.Invoke();
            return clicked;
        }
        return CenteredSmallButton(fallback, id, color, matchPanelBg);
    }

    private float CalcSmallButtonWidth(string label)
    {
        var style = ImGui.GetStyle();
        return ImGui.CalcTextSize(label).X + style.FramePadding.X * 2f;
    }

    private bool SquareIconButton(string icon, string fallback, string id, bool matchPanelBg = true)
    {
        float size = ImGui.GetFrameHeight();
        int styleCount = 0;
        if (matchPanelBg)
        {
            var style = ImGui.GetStyle();
            var baseColor = style.Colors[(int)ImGuiCol.ChildBg];
            ImGui.PushStyleColor(ImGuiCol.Button, baseColor);
            ImGui.PushStyleColor(ImGuiCol.ButtonHovered, Tint(baseColor, 0.04f));
            ImGui.PushStyleColor(ImGuiCol.ButtonActive, Tint(baseColor, -0.04f));
            styleCount = 3;
        }
        if (_iconFontLoaded)
        {
            _pushIconFont?.Invoke();
            bool clicked = ImGui.Button($"{icon}##{id}", new Vector2(size, size));
            _popIconFont?.Invoke();
            if (styleCount > 0)
                ImGui.PopStyleColor(styleCount);
            return clicked;
        }
        bool fallbackClicked = ImGui.Button($"{fallback}##{id}", new Vector2(size, size));
        if (styleCount > 0)
            ImGui.PopStyleColor(styleCount);
        return fallbackClicked;
    }

    private bool SmallIconButton(string icon, string fallback, string id, bool matchPanelBg = true)
    {
        int styleCount = 0;
        if (matchPanelBg)
        {
            var style = ImGui.GetStyle();
            var baseColor = style.Colors[(int)ImGuiCol.ChildBg];
            ImGui.PushStyleColor(ImGuiCol.Button, baseColor);
            ImGui.PushStyleColor(ImGuiCol.ButtonHovered, Tint(baseColor, 0.04f));
            ImGui.PushStyleColor(ImGuiCol.ButtonActive, Tint(baseColor, -0.04f));
            styleCount = 3;
        }
        if (_iconFontLoaded)
        {
            _pushIconFont?.Invoke();
            bool clicked = ImGui.SmallButton($"{icon}##{id}");
            _popIconFont?.Invoke();
            if (styleCount > 0)
                ImGui.PopStyleColor(styleCount);
            return clicked;
        }
        bool fallbackClicked = ImGui.SmallButton($"{fallback}##{id}");
        if (styleCount > 0)
            ImGui.PopStyleColor(styleCount);
        return fallbackClicked;
    }

    private bool SmallAccentIconButton(string icon, string fallback, string id)
    {
        var style = ImGui.GetStyle();
        var baseColor = style.Colors[(int)ImGuiCol.ChildBg];
        var hover = Tint(baseColor, 0.04f);
        var active = Tint(baseColor, -0.04f);
        ImGui.PushStyleColor(ImGuiCol.Button, baseColor);
        ImGui.PushStyleColor(ImGuiCol.ButtonHovered, hover);
        ImGui.PushStyleColor(ImGuiCol.ButtonActive, active);
        bool clicked = SmallIconButton(icon, fallback, id);
        ImGui.PopStyleColor(3);
        return clicked;
    }
private void DrawSessionsList()
{
    // Header left: title + refresh
    ImGui.TextDisabled("Sessions");
    ImGui.SameLine();
    if (SmallAccentIconButton("\uf021", "Refresh", "sessions-refresh"))
        RequestSessionsRefresh(true);

    // Venue name (only when API key is present)
    if (HasAdminKey() && !string.IsNullOrWhiteSpace(Plugin.Config.CurrentVenueName))
    {
        ImGui.SameLine();
        ImGui.TextDisabled($"Venue: {Plugin.Config.CurrentVenueName}");
    }

	    // Right-aligned header buttons (Connect / New Game / Defaults / Settings)
	    float rightEdge = ImGui.GetWindowContentRegionMax().X;
	    // Add breathing room so the last button never hugs the far right edge.
	    // This addresses both connected and disconnected layouts.
	    float rightPad = Math.Max(6f, ImGui.CalcTextSize(" ").X);
	    rightEdge = Math.Max(0f, rightEdge - rightPad);

    // Use icons that are very likely to exist in your FA font merge:
    // - Connect: plug (U+F1E6) fallback text if font not loaded
    // - New Game: plus (U+F067) fallback text if font not loaded
    // - Defaults: user (U+F007) already used elsewhere
    // - Settings: cog (U+F013)
    string connectLabel  = _iconFontLoaded ? "\uf090" : "Connect";  // fa-plug
    string newGameLabel  = _iconFontLoaded ? "\uf11b" : "Games"; // fa-gamepad
    string defaultsGlyph = "\uf007";
    string settingsGlyph = "\uf013";

    float iconW = ImGui.GetFrameHeight();
    float connectW = CalcSmallButtonWidth(connectLabel);
    float newGameW  = CalcSmallButtonWidth(newGameLabel);

    // We always reserve space for the 4 buttons; connect is shown only when relevant.
    bool showConnect = !Plugin.Config.BingoConnected && _permissionsChecked;

    float totalW = 0f;
    if (showConnect) totalW += connectW + 4f;
    totalW += newGameW + 4f;
    totalW += iconW + 4f; // defaults square
    totalW += iconW + 0f; // settings square

    ImGui.SameLine();
    ImGui.SetCursorPosX(Math.Max(0f, rightEdge - totalW));

    var headerBg = ImGui.GetStyle().Colors[(int)ImGuiCol.ChildBg];
    ImGui.PushStyleColor(ImGuiCol.Button, headerBg);
    ImGui.PushStyleColor(ImGuiCol.ButtonHovered, Tint(headerBg, 0.04f));
    ImGui.PushStyleColor(ImGuiCol.ButtonActive, Tint(headerBg, -0.04f));

    // Connect button uses SAME logic as Settings window "Reconnect"
    if (showConnect)
    {
        if (SmallIconButton("\uf0c1", connectLabel, "connect-bingo"))
        {
            // Mirror ConfigWindow reconnect behaviour
            _ = Plugin.ConnectToServerAsync();
        }

        if (ImGui.IsItemHovered())
            ImGui.SetTooltip("Connect Bingo (admin)");

        ImGui.SameLine();
    }

    // "New Game" button (replaces dice that didn't render)
    if (ImGui.SmallButton(newGameLabel))
    {
        if (!_rightPaneCollapsed && _topView == TopView.Games)
        {
            SetRightPaneCollapsed(true);
        }
        else
        {
            _topView = TopView.Games;
            if (_rightPaneCollapsed)
                SetRightPaneCollapsed(false);
        }
    }
    if (ImGui.IsItemHovered())
        ImGui.SetTooltip("Create / manage game sessions");

    ImGui.SameLine();
    if (SquareIconButton(defaultsGlyph, "Defaults", "defaults"))
        ImGui.OpenPopup("DefaultsPopup");

    ImGui.SameLine();
    if (SquareIconButton(settingsGlyph, "Settings", "settings"))
        Plugin.ToggleConfigUI();

    ImGui.PopStyleColor(3);

    // Event selector line
    ImGui.Spacing();
    if (HasAdminKey())
    {
        ImGui.TextDisabled("Event");
        ImGui.SameLine();
        if (string.IsNullOrWhiteSpace(_activeEventCode))
        {
            if (ImGui.SmallButton("Select Event"))
            {
                _eventSelectorOpen = true;
                if (Plugin.EventsApi != null)
                    _ = Events_LoadList();
                ImGui.OpenPopup("Event Selector");
            }
        }
        else
        {
            ImGui.TextUnformatted($"{_activeEventName} ({_activeEventCode})");
            ImGui.SameLine();
            if (ImGui.SmallButton("Change"))
            {
                _eventSelectorOpen = true;
                if (Plugin.EventsApi != null)
                    _ = Events_LoadList();
                ImGui.OpenPopup("Event Selector");
            }
            ImGui.SameLine();
            if (ImGui.SmallButton("Clear"))
            {
                _activeEventCode = "";
                _activeEventName = "";
                _selectedEvent = null;
                _eventGames.Clear();
                Plugin.Config.LastEventCode = null;
                Plugin.Config.Save();
            }
        }
        DrawEventSelectorPopup();
    }
    else
    {
        ImGui.TextDisabled("Event (API key required)");
    }

    // Defaults popup (unchanged)
    if (ImGui.BeginPopup("DefaultsPopup"))
    {
        ImGui.TextDisabled("Defaults for new game sessions");
        ImGui.Separator();

        var defaults = GetCharacterDefaults();
        var currency = defaults.CurrencyLabel ?? "gil";
        ImGui.SetNextItemWidth(200f);
        if (ImGui.InputText("Currency label", ref currency, 64))
        {
            defaults.CurrencyLabel = string.IsNullOrWhiteSpace(currency) ? null : currency.Trim();
            SaveCharacterDefaults(defaults);
        }

        int pot = defaults.RequiredAmount;
        ImGui.SetNextItemWidth(120f);
        if (ImGui.InputInt("Required amount", ref pot))
        {
            defaults.RequiredAmount = Math.Max(0, pot);
            SaveCharacterDefaults(defaults);
        }

        var bgUrl = defaults.BackgroundImageUrl ?? "";
        ImGui.SetNextItemWidth(280f);
        if (ImGui.InputText("Background image URL", ref bgUrl, 512))
        {
            defaults.BackgroundImageUrl = string.IsNullOrWhiteSpace(bgUrl) ? null : bgUrl.Trim();
            SaveCharacterDefaults(defaults);
        }

        if (ImGui.Button("Close"))
            ImGui.CloseCurrentPopup();

        ImGui.EndPopup();
    }

        ImGui.Spacing();
        if (!_permissionsChecked && !_permissionsLoading)
            _ = Permissions_Load();

        ImGui.SetNextItemWidth(80f);
        if (ImGui.BeginCombo("Type", _sessionFilterCategory.ToString()))
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
        ImGui.SetNextItemWidth(80f);
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
        float tableHeight = Math.Max(0f, ImGui.GetContentRegionAvail().Y);
        if (sessions.Count == 0)
        {
            ImGui.TextDisabled("No sessions.");
        }
        else
        {
            var tableFlags = ImGuiTableFlags.RowBg
                | ImGuiTableFlags.BordersInnerV
                | ImGuiTableFlags.ScrollY;
            if (!Plugin.Config.IsConfigWindowMovable)
                tableFlags |= ImGuiTableFlags.Resizable;
            if (ImGui.BeginTable("SessionsTable", 5, tableFlags, new Vector2(0, tableHeight)))
            {
                float typeW = ImGui.CalcTextSize("Type").X + 14f;
                float statusW = ImGui.CalcTextSize("Status").X + 14f;
                float modeW = ImGui.CalcTextSize("Mode").X + 14f;
                float closeW = ImGui.CalcTextSize("Close").X + 14f;
                ImGui.TableSetupColumn("Type", ImGuiTableColumnFlags.WidthFixed, typeW);
                ImGui.TableSetupColumn("Game", ImGuiTableColumnFlags.WidthStretch);
                ImGui.TableSetupColumn("Status", ImGuiTableColumnFlags.WidthFixed, statusW);
                ImGui.TableSetupColumn("Mode", ImGuiTableColumnFlags.WidthFixed, modeW);
                ImGui.TableSetupColumn("Close", ImGuiTableColumnFlags.WidthFixed, closeW);
                ImGui.TableHeadersRow();

            var style = ImGui.GetStyle();
            for (int i = 0; i < sessions.Count; i++)
            {
                var s = sessions[i];
                ImGui.TableNextRow();
                ImGui.TableNextColumn();
                DrawCenteredIconText(s.TypeIcon, TypeFallback(s.Category), CategoryColor(s.Category));
                ImGui.TableNextColumn();
                    if (ImGui.Selectable(s.Name, _selectedSessionId == s.Id))
                    {
                        _selectedSessionId = s.Id;
                        SelectSession(s);
                    }
                    ImGui.TableNextColumn();
                    DrawCenteredIconText(StatusIcon(s.Status), StatusFallback(s.Status), StatusColor(s.Status));
                    ImGui.TableNextColumn();
                DrawCenteredIconText(ModeIcon(s.Managed), ModeFallback(s.Managed), ModeColor(s.Managed));
                ImGui.TableNextColumn();
                using (var dis = ImRaii.Disabled(!s.CanClose))
                {
                    var color = s.CanClose
                        ? new Vector4(0.95f, 0.95f, 0.95f, 1f)
                        : new Vector4(0.55f, 0.55f, 0.55f, 1f);
                    var rowBg = style.Colors[(int)ImGuiCol.TableRowBg];
                    var rowAlt = style.Colors[(int)ImGuiCol.TableRowBgAlt];
                    var baseBg = (i % 2 == 0 ? rowBg : rowAlt);
                    if (baseBg.W < 0.05f)
                        baseBg = style.Colors[(int)ImGuiCol.ChildBg];
                    ImGui.PushStyleColor(ImGuiCol.Button, baseBg);
                    ImGui.PushStyleColor(ImGuiCol.ButtonHovered, Tint(baseBg, 0.04f));
                    ImGui.PushStyleColor(ImGuiCol.ButtonActive, Tint(baseBg, -0.04f));
                    bool closed = CenteredIconButton("\uf1f8", "X", $"close-{s.Id}", color);
                    ImGui.PopStyleColor(3);
                    if (closed)
                        _ = CloseSession(s);
                }
            }
                ImGui.EndTable();
            }
        }
    }


private void DrawPermissionsStatusFooter()
{
    float frameH = ImGui.GetFrameHeight();
    float spacingY = ImGui.GetStyle().ItemSpacing.Y;

    // We emit TWO ImGui items vertically: Dummy(frameH) + Text(frameH),
    // plus the default ItemSpacing between them.
    float totalH = frameH + spacingY + frameH;

    float availH = ImGui.GetContentRegionAvail().Y;

    // If this is a footer, bottom-align is usually the most robust (never clips).
    // If you prefer centered-in-remaining-space, replace this with:
    // float offsetY = Math.Max(0f, (availH - totalH) * 0.5f);
    float offsetY = Math.Max(0f, availH - totalH);

    ImGui.SetCursorPosY(ImGui.GetCursorPosY() + offsetY);

    ImGui.AlignTextToFramePadding();

    float lineHeight = ImGui.GetTextLineHeight();

    var currentKey = Plugin.Config.BingoApiKey ?? "";
    if (!string.Equals(currentKey, _permissionsLastKey, StringComparison.Ordinal))
    {
        _permissionsLastKey = currentKey;
        _permissionsBlockedUntilKeyChange = false;
        _permissionsChecked = false;
        _permissionsStatus = "";
    }

    if (string.IsNullOrWhiteSpace(currentKey))
    {
        _permissionsStatus = "Admin key missing; managed sessions hidden.";
        _permissionsChecked = true;
        _permissionsBlockedUntilKeyChange = true;
    }

    if (!_permissionsChecked && !_permissionsLoading && !_permissionsBlockedUntilKeyChange)
        _ = Permissions_Load();

    var statusText = _permissionsLoading
        ? "Checking permissions..."
        : (_permissionsStatus ?? "");

    bool isConnected = !_permissionsLoading && _allowedScopes.Count > 0;

    bool isFailed = _permissionsBlockedUntilKeyChange
        && statusText.Contains("failed", StringComparison.OrdinalIgnoreCase);

    if (isFailed)
        statusText = "Disconnected";

    var dotColor = _permissionsLoading
        ? new Vector4(0.90f, 0.70f, 0.20f, 1.0f)
        : (isFailed
            ? new Vector4(0.90f, 0.25f, 0.25f, 1.0f)
            : (isConnected
                ? new Vector4(0.20f, 0.85f, 0.45f, 1.0f)
                : new Vector4(0.70f, 0.70f, 0.70f, 1.0f)));

    // Draw the dot using the draw list (does not affect layout)
    var draw = ImGui.GetWindowDrawList();
    float radius = lineHeight * 0.25f;
    var start = ImGui.GetCursorScreenPos();
    var center = new Vector2(start.X + radius, start.Y + frameH * 0.5f);

    draw.AddCircleFilled(center, radius, ImGui.ColorConvertFloat4ToU32(dotColor));

    var highlight = Tint(dotColor, 0.20f);
    var shadow = Tint(dotColor, -0.20f);

    draw.AddCircleFilled(
        new Vector2(center.X - radius * 0.35f, center.Y - radius * 0.35f),
        radius * 0.55f,
        ImGui.ColorConvertFloat4ToU32(highlight)
    );

    draw.AddCircleFilled(
        new Vector2(center.X + radius * 0.25f, center.Y + radius * 0.25f),
        radius * 0.45f,
        ImGui.ColorConvertFloat4ToU32(shadow)
    );

    // Reserve layout space for the dot row
    ImGui.Dummy(new Vector2(radius * 2f + 4f, frameH));

    ImGui.SameLine();

    // Render the status text on the same row
    ImGui.TextDisabled(string.IsNullOrWhiteSpace(statusText)
        ? "Permissions status unavailable."
        : statusText);
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
            SessionCategory.Casino => "C",
            SessionCategory.Draw => "D",
            SessionCategory.Party => "P",
            _ => "-",
        };
    }

    private static string CategoryHeaderIcon(SessionCategory category)
    {
        return category switch
        {
            SessionCategory.Casino => "\uf522", // dice
            SessionCategory.Draw => "\uf06b", // gift (match sessions list)
            SessionCategory.Party => "\uf0c0", // users
            _ => "",
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

        bool hasApiKey = HasAdminKey();
        bool filterByEvent = !string.IsNullOrWhiteSpace(_activeEventCode);
        var eventCardgames = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        if (filterByEvent)
        {
            foreach (var g in _eventGames)
            {
                if (!string.Equals(g.Module, "cardgames", StringComparison.OrdinalIgnoreCase))
                    continue;
                if (!string.IsNullOrWhiteSpace(g.JoinCode))
                    eventCardgames.Add(g.JoinCode);
            }
        }

        foreach (var s in _cardgamesSessions)
        {
            if (s is null) continue;
            if (!hasApiKey)
                continue;
            if (filterByEvent && !eventCardgames.Contains(s.join_code))
                continue;
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
                GameId = s.game_id,
                TypeIcon = TypeIcon(SessionCategory.Casino),
                CanClose = true
            });
        }

        foreach (var g in _bingoGames)
        {
            if (!hasApiKey)
                continue;
            if (filterByEvent)
                continue;
            var id = g.game_id ?? "";
            var title = string.IsNullOrWhiteSpace(g.title) ? id : g.title;
            var label = string.IsNullOrWhiteSpace(title) ? "Bingo" : $"Bingo: {title}";
            list.Add(new SessionEntry
            {
                Id = $"bingo-{id}",
                Name = label,
                Status = g.active ? "Live" : "Finished",
                Category = SessionCategory.Party,
                Managed = true,
                TargetView = View.Bingo,
                GameId = id,
                TypeIcon = TypeIcon(SessionCategory.Party),
                CanClose = g.active
            });
        }

        if (_huntState?.hunt is not null)
        {
            if (!hasApiKey)
                return list.Where(ApplySessionFilters).ToList();
            if (filterByEvent)
                return list.Where(ApplySessionFilters).ToList();
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
                GameId = hunt.hunt_id,
                TypeIcon = TypeIcon(SessionCategory.Party),
                CanClose = hunt.active && !hunt.ended
            });
        }

        if (Plugin.Config.CurrentGame is not null)
        {
            if (filterByEvent)
                return list.Where(ApplySessionFilters).ToList();
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
                Index = Plugin.Config.CurrentGameIndex,
                TypeIcon = TypeIcon(SessionCategory.Party),
                CanClose = false
            });
        }

        if (Plugin.Config.GlamRoulette is not null)
        {
            if (filterByEvent)
                return list.Where(ApplySessionFilters).ToList();
            var glam = Plugin.Config.GlamRoulette;
            var status = glam.RoundActive ? "Live" : "Waiting";
            list.Add(new SessionEntry
            {
                Id = "glam",
                Name = string.IsNullOrWhiteSpace(glam.Title) ? "Glam Competition" : glam.Title,
                Status = status,
                Category = SessionCategory.Party,
                Managed = false,
                TargetView = View.Glam,
                TypeIcon = TypeIcon(SessionCategory.Party),
                CanClose = false
            });
        }

        if (Plugin.Config.Raffle is not null)
        {
            if (filterByEvent)
                return list.Where(ApplySessionFilters).ToList();
            var raffle = Plugin.Config.Raffle;
            var status = raffle.IsOpen ? "Live" : "Waiting";
            list.Add(new SessionEntry
            {
                Id = "raffle",
                Name = string.IsNullOrWhiteSpace(raffle.Title) ? "Raffle" : raffle.Title,
                Status = status,
                Category = SessionCategory.Draw,
                Managed = false,
                TargetView = View.Raffle,
                TypeIcon = TypeIcon(SessionCategory.Draw),
                CanClose = false
            });
        }

        if (Plugin.Config.SpinWheel is not null)
        {
            if (filterByEvent)
                return list.Where(ApplySessionFilters).ToList();
            list.Add(new SessionEntry
            {
                Id = "wheel",
                Name = string.IsNullOrWhiteSpace(Plugin.Config.SpinWheel.Title) ? "Spin Wheel" : Plugin.Config.SpinWheel.Title,
                Status = "Ready",
                Category = SessionCategory.Draw,
                Managed = false,
                TargetView = View.SpinWheel,
                TypeIcon = TypeIcon(SessionCategory.Draw),
                CanClose = false
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
        if (_rightPaneCollapsed)
            SetRightPaneCollapsed(false);
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
        else if (entry.TargetView == View.Events)
        {
            if (_currentVenue == null)
                _ = Venue_LoadCurrent();
            _ = Events_LoadList();
        }
        else if (entry.TargetView == View.MurderMystery && entry.Index.HasValue)
        {
            Plugin.Config.CurrentGameIndex = entry.Index.Value;
            Plugin.Config.Save();
        }
    }

    private async Task CloseSession(SessionEntry entry)
    {
        switch (entry.TargetView)
        {
            case View.Cardgames:
                if (entry.Cardgame is null)
                    return;
                await Cardgames_CloseSession(entry.Cardgame);
                break;
            case View.Bingo:
                if (!string.IsNullOrWhiteSpace(entry.GameId))
                    await Bingo_EndGame(entry.GameId);
                break;
            case View.Hunt:
                if (!string.IsNullOrWhiteSpace(entry.GameId))
                    await Hunt_EndGame(entry.GameId);
                break;
        }
        RequestSessionsRefresh(true);
    }

    private bool HasAdminKey()
    {
        return !string.IsNullOrWhiteSpace(Plugin.Config.BingoApiKey);
    }

    private void SetRightPaneCollapsed(bool collapsed, bool force = false)
    {
        if (!force && _rightPaneCollapsed == collapsed)
            return;
        _rightPaneCollapsed = collapsed;
        if (_rememberRightPaneState)
        {
            Plugin.Config.RightPaneCollapsed = _rightPaneCollapsed;
            Plugin.Config.Save();
        }

        var size = ImGui.GetWindowSize();
        var contentWidth = ImGui.GetWindowContentRegionMax().X - ImGui.GetWindowContentRegionMin().X;
        _windowExtraWidth = Math.Max(0f, size.X - contentWidth);
        if (_rightPaneCollapsed)
        {
            _lastExpandedWidth = size.X;
            _pendingWindowWidth = Math.Max(MinWindowWidthCollapsed, _leftPaneWidth + _windowExtraWidth);
            SizeConstraints = new WindowSizeConstraints
            {
                MinimumSize = new Vector2(MinWindowWidthCollapsed, MinWindowHeight),
                MaximumSize = new Vector2(float.MaxValue, float.MaxValue)
            };
        }
        else
        {
            float targetWidth = _lastExpandedWidth > 0f ? _lastExpandedWidth : size.X + 240f;
            _pendingWindowWidth = Math.Max(MinWindowWidthExpanded, targetWidth);
            SizeConstraints = new WindowSizeConstraints
            {
                MinimumSize = new Vector2(MinWindowWidthExpanded, MinWindowHeight),
                MaximumSize = new Vector2(float.MaxValue, float.MaxValue)
            };
        }
        _pendingWindowResize = true;
    }

    private void MarkRightPaneRemembered()
    {
        if (_rememberRightPaneState)
            return;
        _rememberRightPaneState = true;
        Plugin.Config.RightPaneRemembered = true;
        Plugin.Config.RightPaneCollapsed = _rightPaneCollapsed;
        Plugin.Config.Save();
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

    private ForestConfig.GameDefaults GetCharacterDefaults()
    {
        if (!Plugin.Config.PerCharacterGameDefaults.TryGetValue(_characterKey, out var defaults))
        {
            defaults = new ForestConfig.GameDefaults
            {
                RequiredAmount = Plugin.Config.CardgamesPreferredPot,
                CurrencyLabel = Plugin.Config.CardgamesPreferredCurrency,
                BackgroundImageUrl = Plugin.Config.CardgamesPreferredBackgroundUrl,
            };
            Plugin.Config.PerCharacterGameDefaults[_characterKey] = defaults;
        }
        return defaults;
    }

        private ForestConfig.GameDefaults GetEffectiveDefaults()
        {
            // Start with character defaults
            var defaults = GetCharacterDefaults();
        
            // Override with venue defaults if available
            if (_currentVenue != null)
            {
                if (!string.IsNullOrWhiteSpace(_currentVenue.CurrencyName))
                    defaults.CurrencyLabel = _currentVenue.CurrencyName;
            
                if (_currentVenue.MinimalSpend.HasValue && _currentVenue.MinimalSpend.Value > 0)
                    defaults.RequiredAmount = _currentVenue.MinimalSpend.Value;
            
                if (!string.IsNullOrWhiteSpace(_currentVenue.BackgroundImage))
                    defaults.BackgroundImageUrl = _currentVenue.BackgroundImage;
            }
        
            return defaults;
        }

    private void LoadCharacterDefaults()
    {
            var defaults = GetEffectiveDefaults();
        _cardgamesPot = defaults.RequiredAmount;
        _cardgamesCurrency = defaults.CurrencyLabel ?? "gil";
        _cardgamesBackgroundUrl = defaults.BackgroundImageUrl ?? "";
    }

    private void SaveCharacterDefaults(ForestConfig.GameDefaults defaults)
    {
        Plugin.Config.PerCharacterGameDefaults[_characterKey] = defaults;
        Plugin.Config.Save();
    }

    private bool HasGamePermissions(string title)
    {
        return title switch
        {
            "Scavenger Hunt" => CanLoadHunt(),
            "Bingo" => CanLoadBingo(),
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
        if (_permissionsBlockedUntilKeyChange)
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
                _permissionsBlockedUntilKeyChange = true;
                return;
            }

            var baseUrl = (Plugin.Config.BingoApiBaseUrl ?? "https://rites.thebigtree.life").TrimEnd('/');
            using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(8) };
            using var req = new HttpRequestMessage(HttpMethod.Get, $"{baseUrl}/api/auth/permissions");
            req.Headers.Add("X-API-Key", apiKey);
            using var resp = await http.SendAsync(req).ConfigureAwait(false);
            var payload = await resp.Content.ReadAsStringAsync().ConfigureAwait(false);

            if (!resp.IsSuccessStatusCode)
            {
                _permissionsStatus = $"Permission check failed: {resp.StatusCode}";
                _permissionsChecked = true;
                _permissionsBlockedUntilKeyChange = true;
                return;
            }

            using var doc = JsonDocument.Parse(payload);
            if (!doc.RootElement.TryGetProperty("ok", out var okEl) || !okEl.GetBoolean())
            {
                _permissionsStatus = "Permission check failed.";
                _permissionsChecked = true;
                _permissionsBlockedUntilKeyChange = true;
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
            _permissionsBlockedUntilKeyChange = true;
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

	    // Don't show the generic "Collapse" bloat for Bingo; the Bingo panel has its own back header.
	    bool showCollapse = _view != View.Bingo && !(_view == View.Cardgames
	        && _cardgamesSelectedSession is not null
	        && _cardgamesSelectedSession.game_id == "blackjack");
        if (showCollapse)
        {
            ImGui.Spacing();
            ImGui.PushStyleColor(ImGuiCol.Button, ImGui.ColorConvertFloat4ToU32(new Vector4(0.92f, 0.78f, 0.30f, 0.95f)));
            ImGui.PushStyleColor(ImGuiCol.ButtonHovered, ImGui.ColorConvertFloat4ToU32(new Vector4(0.98f, 0.84f, 0.35f, 1.0f)));
            ImGui.PushStyleColor(ImGuiCol.ButtonActive, ImGui.ColorConvertFloat4ToU32(new Vector4(0.82f, 0.68f, 0.25f, 1.0f)));
            if (ImGui.SmallButton("Collapse"))
            {
                ImGui.PopStyleColor(3);
                _controlSurfaceOpen = false;
                SetRightPaneCollapsed(true);
                ImGui.EndChild();
                ImGui.PopStyleVar();
                return;
            }
            ImGui.PopStyleColor(3);
            ImGui.Separator();
        }

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

        if (_view != View.Bingo && !(_view == View.Cardgames
            && _cardgamesSelectedSession is not null
            && _cardgamesSelectedSession.game_id == "blackjack"))
        {
            DrawSessionHeader();
            ImGui.Spacing();

            DrawPlayerFunnelBlock();
            ImGui.Spacing();
            DrawLiveReassuranceBlock();

            ImGui.Separator();
        }
        switch (_view)
        {
            case View.Cardgames: DrawCardgamesPanel(); break;
            case View.Bingo: ImGui.PushStyleColor(ImGuiCol.ChildBg, ImGui.ColorConvertFloat4ToU32(CategoryColor(SessionCategory.Party))); DrawBingoAdminPanel(); ImGui.PopStyleColor(); break;
            case View.Hunt: DrawHuntPanel(); break;
            case View.MurderMystery: DrawMurderMysteryPanel(); break;
            case View.Raffle: DrawRafflePanel(); break;
            case View.SpinWheel: DrawSpinWheelPanel(); break;
            case View.Glam: DrawGlamRoulettePanel(); break;
                case View.Events: DrawEventsPanel(); break;
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
        ImGui.Indent(GameCardTitlePaddingLeft);
        if (SmallIconButton("\uf053", "<", "collapse-games"))
            SetRightPaneCollapsed(true);
        ImGui.SameLine(0, 6f);
        ImGui.TextUnformatted("Games");
        ImGui.TextDisabled("Choose a game template, then prepare or start a session.");
        ImGui.Separator();
        ImGui.Unindent(GameCardTitlePaddingLeft);

        DrawGameSection(SessionCategory.Party, "Party Games",
            "Experiences run during gatherings and ceremonies.",
            new[]
            {
                new GameCard("Scavenger Hunt", SessionCategory.Party, true, true, false, "Managed staff-led hunt with shared locations."),
                new GameCard("Murder Mystery", SessionCategory.Party, false, false, false, "Local story and text management."),
                new GameCard("Glam Competition", SessionCategory.Party, false, false, true, "Local voting with themed prompts and online lists."),
                new GameCard("Bingo", SessionCategory.Party, true, false, false, "Managed bingo with live calls.")
            });

        DrawGameSection(SessionCategory.Casino, "Casino Games",
            "Managed tables with join keys and shared decks.",
            new[]
            {
                new GameCard("Blackjack", SessionCategory.Casino, true, true, true, "Managed blackjack table."),
                new GameCard("Poker", SessionCategory.Casino, true, true, true, "Managed Texas Hold'em table."),
                new GameCard("High/Low", SessionCategory.Casino, true, true, true, "Managed high/low rounds.")
            });

        DrawGameSection(SessionCategory.Draw, "Draws & Giveaways",
            "Lightweight draws and rolling events.",
            new[]
            {
                new GameCard("Raffle", SessionCategory.Draw, false, false, false, "Local raffle draw."),
                new GameCard("Spin Wheel", SessionCategory.Draw, false, false, false, "Local wheel spin (managed later).")
            });
    }

    private void OpenCardgamesCreatePopup(string gameId)
    {
        _cardgamesCreateGameId = gameId;
        _cardgamesGameId = gameId;
        _cardgamesCreatePopupPending = true;
        _cardgamesCreateWindowOpen = true;
        _cardgamesStatus = "";
        Plugin.Config.CardgamesLastGameId = gameId;
        Plugin.Config.Save();
        if (CanLoadCardgames())
        {
            _ = Cardgames_LoadDecks();
            _ = Cardgames_LoadSessions();
        }
        var defaults = GetCharacterDefaults();
        _cardgamesPot = defaults.RequiredAmount;
        _cardgamesCurrency = defaults.CurrencyLabel ?? "gil";
        _cardgamesBackgroundUrl = defaults.BackgroundImageUrl ?? "";
    }

    private void DrawCardgamesCreateWindow()
    {
        if (!_cardgamesCreateWindowOpen)
            return;
        if (_cardgamesCreatePopupPending)
            _cardgamesCreatePopupPending = false;
        ImGui.SetNextWindowPos(ImGui.GetMainViewport().GetCenter(), ImGuiCond.Appearing, new Vector2(0.5f, 0.5f));
        ImGui.SetNextWindowSize(new Vector2(520f, 0f), ImGuiCond.Appearing);
        ImGui.PushStyleColor(ImGuiCol.WindowBg, ImGui.ColorConvertFloat4ToU32(new Vector4(0.08f, 0.09f, 0.10f, 0.98f)));
        if (!ImGui.Begin("Prepare cardgame session", ref _cardgamesCreateWindowOpen, ImGuiWindowFlags.NoCollapse | ImGuiWindowFlags.AlwaysAutoResize))
        {
            ImGui.End();
            ImGui.PopStyleColor();
            return;
        }

        ImGui.TextUnformatted($"Prepare {FormatCardgamesName(_cardgamesCreateGameId)}");
        ImGui.TextDisabled("Sessions stay idle until started.");
        ImGui.Separator();

        ImGui.TextDisabled("Deck");
        ImGui.SetNextItemWidth(280f);
        string deckLabel = string.IsNullOrWhiteSpace(_cardgamesSelectedDeckId) ? "(default deck)" : _cardgamesSelectedDeckId;
        if (ImGui.BeginCombo("##CardgamesDeck", deckLabel))
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
        ImGui.SameLine();
        using (var dis = ImRaii.Disabled(_cardgamesDecksLoading))
        {
            if (SmallIconButton("\uf021", "Refresh", "cardgames-decks-refresh"))
                _ = Cardgames_LoadDecks();
        }

        ImGui.TextDisabled("Currency");
        ImGui.SameLine();
        ImGui.SetNextItemWidth(120f);
        string currency = _cardgamesCurrency;
        if (ImGui.InputText("##CardgamesCurrency", ref currency, 32))
        {
            _cardgamesCurrency = string.IsNullOrWhiteSpace(currency) ? "gil" : currency.Trim();
            var defaults = GetCharacterDefaults();
            defaults.CurrencyLabel = _cardgamesCurrency;
            SaveCharacterDefaults(defaults);
        }

        ImGui.SameLine();
        int pot = Math.Max(0, _cardgamesPot);
        ImGui.SetNextItemWidth(110f);
        if (ImGui.InputInt("##CardgamesPot", ref pot))
        {
            _cardgamesPot = Math.Max(0, pot);
            var defaults = GetCharacterDefaults();
            defaults.RequiredAmount = _cardgamesPot;
            SaveCharacterDefaults(defaults);
        }

        var backgrounds = _cardgamesSessions
            .Select(s => s.background_url)
            .Where(url => !string.IsNullOrWhiteSpace(url))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToList();
        string bgLabel = string.IsNullOrWhiteSpace(_cardgamesBackgroundUrl) ? "(none)" : _cardgamesBackgroundUrl;
        ImGui.SetNextItemWidth(360f);
        if (ImGui.BeginCombo("Background", bgLabel))
        {
            if (ImGui.Selectable("(none)", string.IsNullOrWhiteSpace(_cardgamesBackgroundUrl)))
            {
                _cardgamesBackgroundUrl = "";
                var defaults = GetCharacterDefaults();
                defaults.BackgroundImageUrl = null;
                SaveCharacterDefaults(defaults);
            }
            foreach (var url in backgrounds)
            {
                bool selected = string.Equals(_cardgamesBackgroundUrl, url, StringComparison.OrdinalIgnoreCase);
                if (ImGui.Selectable(url, selected))
                {
                    _cardgamesBackgroundUrl = url;
                    var defaults = GetCharacterDefaults();
                    defaults.BackgroundImageUrl = _cardgamesBackgroundUrl;
                    SaveCharacterDefaults(defaults);
                }
            }
            ImGui.EndCombo();
        }

        ImGui.SetNextItemWidth(360f);
        string bgUrl = _cardgamesBackgroundUrl;
        if (ImGui.InputText("Custom URL", ref bgUrl, 512))
        {
            _cardgamesBackgroundUrl = bgUrl.Trim();
            var defaults = GetCharacterDefaults();
            defaults.BackgroundImageUrl = string.IsNullOrWhiteSpace(_cardgamesBackgroundUrl) ? null : _cardgamesBackgroundUrl;
            SaveCharacterDefaults(defaults);
        }

        ImGui.Spacing();
        using (var dis = ImRaii.Disabled(_cardgamesLoading))
        {
            if (ImGui.Button("Create session"))
            {
                _cardgamesOpenAfterCreate = true;
                _cardgamesOpenAfterCreate = true;
                _ = Cardgames_CreateSession(true);
                _cardgamesCreateWindowOpen = false;
            }
        }
        ImGui.SameLine();
        if (ImGui.Button("Cancel"))
            _cardgamesCreateWindowOpen = false;

        ImGui.End();
        ImGui.PopStyleColor();
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

    private void DrawGameSection(SessionCategory category, string title, string description, GameCard[] cards)
    {
        const float cardRowHeight = 84f;
        var padding = new Vector2(SectionHeaderPaddingX, 12f);
        var titleSize = ImGui.CalcTextSize(title);
        var descSize = ImGui.CalcTextSize(description);
        float blockHeight = padding.Y * 2f + titleSize.Y + descSize.Y + 8f
            + cards.Length * (cardRowHeight + 8f);

        ImGui.Spacing();
        ImGui.BeginChild($"Section_{title}", new Vector2(0, blockHeight), false, ImGuiWindowFlags.NoScrollbar | ImGuiWindowFlags.NoScrollWithMouse);
        var draw = ImGui.GetWindowDrawList();
        var pos = ImGui.GetWindowPos();
        var size = ImGui.GetWindowSize();
        var accent = CategoryColor(cards.Length > 0 ? cards[0].Category : category);
        var bg = new Vector4(accent.X * 0.15f, accent.Y * 0.15f, accent.Z * 0.15f, 0.85f);
        var border = new Vector4(accent.X, accent.Y, accent.Z, 0.40f);
        draw.AddRectFilled(pos, new Vector2(pos.X + size.X, pos.Y + size.Y), ImGui.ColorConvertFloat4ToU32(bg), 8f);
        draw.AddRect(pos, new Vector2(pos.X + size.X, pos.Y + size.Y), ImGui.ColorConvertFloat4ToU32(border), 8f, 0, 1.2f);

        ImGui.SetCursorPos(padding);
        DrawSectionHeader(category, title, description);
        ImGui.Spacing();
        float inset = GameCardInset;
        foreach (var card in cards)
        {
            var cur = ImGui.GetCursorPos();
            ImGui.SetCursorPos(new Vector2(cur.X + inset, cur.Y));
            float width = Math.Max(0f, ImGui.GetContentRegionAvail().X - inset);
            DrawGameCard(card, cardRowHeight, width);
            ImGui.Spacing();
        }
        ImGui.EndChild();
    }

    private void DrawGameCard(GameCard card, float rowHeight, float width)
    {
        ImGui.BeginChild($"GameCard_{card.Title}", new Vector2(width, rowHeight), false, ImGuiWindowFlags.NoScrollbar | ImGuiWindowFlags.NoScrollWithMouse);
        var draw = ImGui.GetWindowDrawList();
        var pos = ImGui.GetWindowPos();
        var size = ImGui.GetWindowSize();
        var accent = CategoryColor(card.Category);
        var bg = new Vector4(0.08f, 0.08f, 0.10f, 0.92f);
        var border = new Vector4(accent.X, accent.Y, accent.Z, 0.55f);
        draw.AddRectFilled(pos, new Vector2(pos.X + size.X, pos.Y + size.Y), ImGui.ColorConvertFloat4ToU32(bg), 6f);
        draw.AddRect(pos, new Vector2(pos.X + size.X, pos.Y + size.Y), ImGui.ColorConvertFloat4ToU32(border), 6f, 0, 1.0f);

        var padding = new Vector2(GameCardTitlePaddingLeft, 4f);
        ImGui.SetCursorPos(padding);
        ImGui.PushStyleVar(ImGuiStyleVar.ItemSpacing, new Vector2(8f, 4f));

        float actionW = 150f;
        float buttonAreaW = actionW + 8f;
        float textWrapX = pos.X + size.X - GameCardPaddingRight - buttonAreaW;
        ImGui.PushTextWrapPos(textWrapX);

        ImGui.TextUnformatted(card.Title);
        float descIndent = Math.Max(0f, GameCardDetailsPaddingLeft - GameCardTitlePaddingLeft);
        ImGui.Indent(descIndent);
        ImGui.TextDisabled(card.Details);

        ImGui.Dummy(new Vector2(2f, 10f));
        DrawBadgeWrapRow(textWrapX - pos.X - padding.X - descIndent,
            new[]
            {
                new BadgeSpec(
                    card.Managed ? "Online" : "Local",
                    card.Managed ? new Vector4(0.30f, 0.65f, 0.70f, 1.0f) : new Vector4(0.40f, 0.75f, 0.55f, 1.0f),
                    card.Managed
                        ? "Runs through the central service (admin key required)."
                        : "Runs locally inside Forest Manager."
                ),
                card.JoinKey ? new BadgeSpec(
                    "Join key needed",
                    new Vector4(0.85f, 0.55f, 0.25f, 1.0f),
                    "Players need a join key to enter this session."
                ) : BadgeSpec.Empty,
                card.InternetAssets ? new BadgeSpec(
                    "Downloads online assets",
                    new Vector4(0.55f, 0.70f, 0.90f, 1.0f),
                    "Downloads shared assets from the internet."
                ) : BadgeSpec.Empty,
            }
        );
        ImGui.Dummy(new Vector2(0, 10f));
        ImGui.Unindent(descIndent);
        ImGui.PopTextWrapPos();

        float buttonY = (rowHeight - 28f) * 0.5f;
        ImGui.SetCursorPos(new Vector2(size.X - GameCardPaddingRight - buttonAreaW, buttonY));
        string actionLabel = card.Managed ? "Prepare session" : "Start";
        if (DrawPrimaryActionButton(actionLabel, card.Managed, card.Title, new Vector2(actionW, 28f)))
        {
            MarkRightPaneRemembered();
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
            bool isCardgame = card.Title is "Blackjack" or "Poker" or "High/Low";
            _controlSurfaceOpen = !isCardgame;
            _topView = isCardgame ? TopView.Games : TopView.Sessions;
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
                    OpenCardgamesCreatePopup(_cardgamesGameId);
                    break;
                case "Poker":
                    _cardgamesGameId = "poker";
                    OpenCardgamesCreatePopup(_cardgamesGameId);
                    break;
                case "High/Low":
                    _cardgamesGameId = "highlow";
                    OpenCardgamesCreatePopup(_cardgamesGameId);
                    break;
                    case "Bingo":
                        _ = Bingo_LoadGames();
                        break;
                case "Raffle":
                    break;
                case "Spin Wheel":
                    break;
            }
        }
        ImGui.Dummy(new Vector2(0, 4f));
        ImGui.PopStyleVar();
        ImGui.EndChild();
    }

    private void DrawSectionHeader(SessionCategory category, string title, string description)
    {
        ImGui.SetWindowFontScale(1.1f);
        var iconColor = CategoryColor(category);
        var icon = CategoryHeaderIcon(category);
        float iconWidth = 0f;
        if (_iconFontLoaded && !string.IsNullOrWhiteSpace(icon))
        {
            _pushIconFont?.Invoke();
            iconWidth = ImGui.CalcTextSize(icon).X;
            ImGui.TextColored(iconColor, icon);
            _popIconFont?.Invoke();
        }
        else
        {
            iconWidth = ImGui.CalcTextSize(CategoryIcon(category)).X;
            ImGui.TextColored(iconColor, CategoryIcon(category));
        }
        ImGui.SameLine();
        ImGui.TextUnformatted(title);
        ImGui.SetWindowFontScale(1.0f);
        float indent = iconWidth + 16f;
        ImGui.Indent(indent);
        ImGui.TextDisabled(description);
        ImGui.Unindent(indent);
    }

    private void DrawBadgeChip(string text, Vector4 color, string tooltip)
    {
        var draw = ImGui.GetWindowDrawList();
        var pos = ImGui.GetCursorScreenPos();
        var textSize = ImGui.CalcTextSize(text);
        var pad = new Vector2(8f, 4f);
        var size = new Vector2(textSize.X + pad.X * 2f, textSize.Y + pad.Y * 2f);
        var bg = new Vector4(color.X, color.Y, color.Z, 0.25f);
        var border = new Vector4(color.X, color.Y, color.Z, 0.55f);
        draw.AddRectFilled(pos, new Vector2(pos.X + size.X, pos.Y + size.Y), ImGui.ColorConvertFloat4ToU32(bg), 8f);
        draw.AddRect(pos, new Vector2(pos.X + size.X, pos.Y + size.Y), ImGui.ColorConvertFloat4ToU32(border), 8f, 0, 1f);
        draw.AddText(new Vector2(pos.X + pad.X, pos.Y + pad.Y), ImGui.ColorConvertFloat4ToU32(new Vector4(0.95f, 0.95f, 0.95f, 1f)), text);
        ImGui.Dummy(size);
        if (!string.IsNullOrWhiteSpace(tooltip) && ImGui.IsItemHovered())
            ImGui.SetTooltip(tooltip);
    }

    private readonly struct BadgeSpec
    {
        public string Text { get; }
        public Vector4 Color { get; }
        public string Tooltip { get; }
        public bool IsEmpty => string.IsNullOrWhiteSpace(Text);
        public BadgeSpec(string text, Vector4 color, string tooltip)
        {
            Text = text;
            Color = color;
            Tooltip = tooltip;
        }
        public static BadgeSpec Empty => new BadgeSpec("", Vector4.Zero, "");
    }

    private void DrawBadgeWrapRow(float maxWidth, BadgeSpec[] badges)
    {
        float used = 0f;
        foreach (var badge in badges)
        {
            if (badge.IsEmpty)
                continue;
            var textSize = ImGui.CalcTextSize(badge.Text);
            var pad = new Vector2(6f, 3f);
            float width = textSize.X + pad.X * 2f;
            if (used > 0f && used + width > maxWidth)
            {
                ImGui.NewLine();
                used = 0f;
            }
            if (used > 0f)
                ImGui.SameLine();
            DrawBadgeChip(badge.Text, badge.Color, badge.Tooltip);
            used += width + 6f;
        }
    }

    private static float Clamp01(float value)
        => value < 0f ? 0f : value > 1f ? 1f : value;

    private static Vector4 Tint(Vector4 color, float delta)
        => new Vector4(
            Clamp01(color.X + delta),
            Clamp01(color.Y + delta),
            Clamp01(color.Z + delta),
            color.W);

    private bool DrawPrimaryActionButton(string label, bool managed, string id, Vector2? size = null)
    {
        var style = ImGui.GetStyle();
        var textSize = ImGui.CalcTextSize(label);
        var buttonSize = size ?? new Vector2(
            textSize.X + style.FramePadding.X * 2f,
            textSize.Y + style.FramePadding.Y * 2f);

        var pos = ImGui.GetCursorScreenPos();
        ImGui.InvisibleButton($"{label}##{id}", buttonSize);
        bool hovered = ImGui.IsItemHovered();
        bool active = ImGui.IsItemActive();
        bool clicked = ImGui.IsItemClicked();

        var baseColor = managed
            ? new Vector4(0.30f, 0.55f, 0.85f, 1.0f)
            : new Vector4(0.35f, 0.70f, 0.50f, 1.0f);
        if (hovered)
            baseColor = Tint(baseColor, 0.06f);
        if (active)
            baseColor = Tint(baseColor, -0.05f);

        var highlight = Tint(baseColor, 0.18f);
        var shadow = Tint(baseColor, -0.18f);
        var border = Tint(baseColor, -0.25f);

        var draw = ImGui.GetWindowDrawList();
        var bottom = new Vector2(pos.X + buttonSize.X, pos.Y + buttonSize.Y);
        float radius = 6f;

        draw.AddRectFilled(pos, bottom, ImGui.ColorConvertFloat4ToU32(baseColor), radius);
        float glossHeight = buttonSize.Y * 0.55f;
        var glossEnd = new Vector2(bottom.X, pos.Y + glossHeight);
        draw.AddRectFilled(pos, glossEnd, ImGui.ColorConvertFloat4ToU32(new Vector4(highlight.X, highlight.Y, highlight.Z, 0.35f)), radius, ImDrawFlags.RoundCornersTop);
        draw.AddRectFilled(new Vector2(pos.X, glossEnd.Y), bottom, ImGui.ColorConvertFloat4ToU32(new Vector4(shadow.X, shadow.Y, shadow.Z, 0.28f)), radius, ImDrawFlags.RoundCornersBottom);
        draw.AddRect(pos, bottom, ImGui.ColorConvertFloat4ToU32(new Vector4(border.X, border.Y, border.Z, 0.9f)), radius, 0, 1f);
        draw.AddRect(new Vector2(pos.X + 1f, pos.Y + 1f), new Vector2(bottom.X - 1f, bottom.Y - 1f),
            ImGui.ColorConvertFloat4ToU32(new Vector4(1f, 1f, 1f, 0.08f)), radius - 1f, 0, 1f);

        var textPos = new Vector2(
            pos.X + (buttonSize.X - textSize.X) * 0.5f,
            pos.Y + (buttonSize.Y - textSize.Y) * 0.5f + (active ? 1f : 0f));
        draw.AddText(textPos, ImGui.ColorConvertFloat4ToU32(new Vector4(0.96f, 0.97f, 0.98f, 1f)), label);

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
            "Bingo" => View.Bingo,
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
        if (_cardgamesSelectedSession is null)
        {
            ImGui.TextUnformatted("Cardgames");
            ImGui.Separator();
            ImGui.TextDisabled("Select a cardgame session from the list.");
            return;
        }

        var selected = _cardgamesSelectedSession;
        var baseUrl = GetCardgamesBaseUrl();
        var playerLink = $"{baseUrl}/cardgames/{selected.game_id}/session/{selected.join_code}";
        bool isCardgameCard = selected.game_id is "blackjack" or "poker" or "highlow";
        if (!isCardgameCard)
        {
            ImGui.TextUnformatted("Cardgames");
            ImGui.Separator();
            ImGui.TextUnformatted($"{FormatCardgamesName(selected.game_id)} session");
            ImGui.TextDisabled($"Status: {selected.status}");
            ImGui.SameLine();
            if (ImGui.Button("Copy player link"))
                ImGui.SetClipboardText(playerLink);
            ImGui.SameLine();
            if (SmallIconButton("\uf24d", "Duplicate", "cardgames-duplicate"))
                _ = Cardgames_CloneSelected();
            ImGui.TextDisabled($"Join: {selected.join_code}");
        }

        if (!string.IsNullOrWhiteSpace(_cardgamesStateError))
            ImGui.TextDisabled(_cardgamesStateError);
        if (_cardgamesStateDoc is null)
        {
            ImGui.TextDisabled("Waiting for state...");
            return;
        }

        JsonDocument? stateDoc = _cardgamesStateDoc;
        if (stateDoc is null)
        {
            ImGui.TextDisabled("Waiting for state...");
            return;
        }
        JsonElement state;
        try
        {
            var root = stateDoc.RootElement;
            if (!root.TryGetProperty("state", out state))
            {
                ImGui.TextDisabled("No state payload.");
                return;
            }
        }
        catch (ObjectDisposedException)
        {
            _cardgamesStateDoc = null;
            ImGui.TextDisabled("Refreshing state...");
            return;
        }

        var status = GetString(state, "status");
        var result = GetString(state, "result");
        var stage = GetString(state, "stage");
        var phase = GetString(state, "phase");
        ImGui.Spacing();

        if (isCardgameCard)
        {
            var cardAccent = CategoryColor(SessionCategory.Casino);
            var cardBg = new Vector4(cardAccent.X * 0.12f, cardAccent.Y * 0.12f, cardAccent.Z * 0.12f, 0.95f);
            var cardBorder = new Vector4(cardAccent.X, cardAccent.Y, cardAccent.Z, 0.55f);
            ImGui.BeginChild("CardgamesCard", Vector2.Zero, false, ImGuiWindowFlags.NoScrollbar | ImGuiWindowFlags.NoScrollWithMouse);
            var cardPos = ImGui.GetWindowPos();
            var cardSize = ImGui.GetWindowSize();
            var cardDraw = ImGui.GetWindowDrawList();
            cardDraw.AddRectFilled(cardPos, new Vector2(cardPos.X + cardSize.X, cardPos.Y + cardSize.Y),
                ImGui.ColorConvertFloat4ToU32(cardBg), 6f);
            cardDraw.AddRect(cardPos, new Vector2(cardPos.X + cardSize.X, cardPos.Y + cardSize.Y),
                ImGui.ColorConvertFloat4ToU32(cardBorder), 6f, 0, 1.2f);

            ImGui.Dummy(new Vector2(0, 6f));
            ImGui.Indent(10f);
            ImGui.PushStyleColor(ImGuiCol.Button, ImGui.ColorConvertFloat4ToU32(new Vector4(0.85f, 0.65f, 0.20f, 0.95f)));
            ImGui.PushStyleColor(ImGuiCol.ButtonHovered, ImGui.ColorConvertFloat4ToU32(new Vector4(0.92f, 0.70f, 0.25f, 1.0f)));
            ImGui.PushStyleColor(ImGuiCol.ButtonActive, ImGui.ColorConvertFloat4ToU32(new Vector4(0.75f, 0.55f, 0.18f, 1.0f)));
            if (SmallIconButton("\uf053", "<", "cardgames-back"))
            {
                ImGui.PopStyleColor(3);
                _controlSurfaceOpen = false;
                SetRightPaneCollapsed(true);
                ImGui.Unindent(10f);
                ImGui.EndChild();
                return;
            }
            ImGui.PopStyleColor(3);
            ImGui.SameLine();
            ImGui.TextUnformatted(FormatCardgamesName(selected.game_id));
            ImGui.SameLine();
            ImGui.TextDisabled($"Session {selected.join_code}");
            ImGui.SameLine();
            if (SmallIconButton("\uf0c5", "Copy", "cardgames-copy"))
                ImGui.SetClipboardText(selected.join_code);
            ImGui.SameLine();
            if (SmallIconButton("\uf0ac", "Web link", "cardgames-copy-link"))
                ImGui.SetClipboardText(playerLink);

            var statusColor = StatusColor(selected.status);
            string turnLabel = selected.status switch
            {
                "live" => (status == "finished" ? "Round complete" : "Host turn"),
                "created" => "Waiting to start",
                "draft" => "Waiting to start",
                "finished" => "Finished",
                _ => "Waiting to start"
            };
            var dotDraw = ImGui.GetWindowDrawList();
            float dotRadius = ImGui.GetTextLineHeight() * 0.25f;
            var dotPos = ImGui.GetCursorScreenPos();
            var dotCenter = new Vector2(dotPos.X + dotRadius, dotPos.Y + ImGui.GetFrameHeight() * 0.5f);
            dotDraw.AddCircleFilled(dotCenter, dotRadius, ImGui.ColorConvertFloat4ToU32(statusColor));
            ImGui.Dummy(new Vector2(dotRadius * 2f + 6f, ImGui.GetFrameHeight()));
            ImGui.SameLine();
            ImGui.TextDisabled(turnLabel);
            if (!string.IsNullOrWhiteSpace(status))
                ImGui.TextDisabled($"Round: {status}");
        if (!string.IsNullOrWhiteSpace(stage) || !string.IsNullOrWhiteSpace(phase))
            ImGui.TextDisabled($"Stage: {FormatGameLabel(stage != "" ? stage : phase)}");
        if (!isCardgameCard && !string.IsNullOrWhiteSpace(status))
            ImGui.TextDisabled($"Round: {status}");
        if (!string.IsNullOrWhiteSpace(result))
            ImGui.TextDisabled($"Result: {result}");
            ImGui.Spacing();
            using (var dis = ImRaii.Disabled(selected.status != "created" && selected.status != "draft"))
            {
                if (ImGui.Button("Start"))
                    _ = Cardgames_StartSelected();
            }
            ImGui.SameLine();
            using (var dis = ImRaii.Disabled(selected.status != "live"))
            {
                if (ImGui.Button("End"))
                    _ = Cardgames_FinishSelected();
            }
            ImGui.SameLine();
            using (var dis = ImRaii.Disabled(selected.status != "live"))
            {
                if (ImGui.Button("Clone + End"))
                    _ = Cardgames_CloneAndFinishSelected();
            }
            ImGui.Spacing();
            ImGui.Dummy(new Vector2(0, 2f));

            if (selected.game_id == "blackjack")
            {
                var hands = GetCardHands(state, "player_hands");
                var handResults = GetStringList(state, "hand_results");
                var multipliers = GetIntList(state, "hand_multipliers");
                if (hands.Count == 0)
                {
                    DrawCardRow("Player hand", GetCardList(state, "player_hand"));
                    ImGui.Spacing();
                }
                else
                {
                    for (int i = 0; i < hands.Count; i++)
                    {
                        var label = $"Player hand {i + 1}";
                        if (i < multipliers.Count && multipliers[i] > 1)
                            label += $" x{multipliers[i]}";
                        if (i < handResults.Count && !string.IsNullOrWhiteSpace(handResults[i]))
                            label += $" ({handResults[i]})";
                        DrawCardRow(label, hands[i]);
                        ImGui.Spacing();
                    }
                }
                DrawCardRow("Dealer hand", GetCardList(state, "dealer_hand"));
                ImGui.Spacing();
                bool live = selected.status == "live";
                using (var dis = ImRaii.Disabled(!live))
                {
                    if (ImGui.Button("Hit"))
                        _ = Cardgames_HostAction("hit");
                    ImGui.SameLine();
                    if (ImGui.Button("Stand"))
                        _ = Cardgames_HostAction("stand");
                    ImGui.SameLine();
                    if (ImGui.Button("Double"))
                        _ = Cardgames_HostAction("double");
                    ImGui.SameLine();
                    if (ImGui.Button("Split"))
                        _ = Cardgames_HostAction("split");
                }
            }
            else if (selected.game_id == "highlow")
            {
                DrawCardRow("Current", GetCardList(state, "current"));
                ImGui.Spacing();
                DrawCardRow("Revealed", GetCardList(state, "revealed"));
                ImGui.Spacing();
                using (var dis = ImRaii.Disabled(selected.status != "live"))
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
            else if (selected.game_id == "poker")
            {
                DrawCardRow("Player hand", GetCardList(state, "player_hand"));
                ImGui.Spacing();
                DrawCardRow("Dealer hand", GetCardList(state, "dealer_hand"));
                ImGui.Spacing();
                DrawCardRow("Community", GetCardList(state, "community"));
                ImGui.Spacing();
                using (var dis = ImRaii.Disabled(selected.status != "live"))
                {
                    if (ImGui.Button("Advance round"))
                        _ = Cardgames_HostAction("advance");
                }
            }

            ImGui.Unindent(10f);
            ImGui.Dummy(new Vector2(0, 6f));
            ImGui.EndChild();
        }
        if (!isCardgameCard)
        {
            ImGui.Spacing();
            using (var dis = ImRaii.Disabled(selected.status != "created" && selected.status != "draft"))
            {
                if (ImGui.Button("Start session"))
                    _ = Cardgames_StartSelected();
            }
            ImGui.SameLine();
            using (var dis = ImRaii.Disabled(selected.status != "live"))
            {
                if (ImGui.Button("Finish session"))
                    _ = Cardgames_FinishSelected();
            }
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
        return (Plugin.Config.BingoApiBaseUrl ?? "https://rites.thebigtree.life").TrimEnd('/');
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
        lock (_cardgamesTextureLock)
        {
            if (_cardgamesTextureCache.TryGetValue(url, out var cached))
            {
                texture = cached;
                return true;
            }
            if (_cardgamesTextureTasks.ContainsKey(url))
                return false;
            _cardgamesTextureTasks[url] = Task.Run(() =>
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
                    var bytes = _cardgamesHttp.GetByteArrayAsync(url).GetAwaiter().GetResult();
                    File.WriteAllBytes(filePath, bytes);
                }
                var tex = Forest.Plugin.TextureProvider.GetFromFile(filePath);
                lock (_cardgamesTextureLock)
                {
                    _cardgamesTextureCache[url] = tex;
                }
            }
            catch (Exception ex)
            {
                Plugin.Log?.Warning($"[Cardgames] Failed to load image {url}: {ex.Message}");
            }
            finally
            {
                lock (_cardgamesTextureLock)
                {
                    _cardgamesTextureTasks.Remove(url);
                }
            }
        });
        }
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

    private static List<List<JsonElement>> GetCardHands(JsonElement state, string key)
    {
        try
        {
            if (state.ValueKind != JsonValueKind.Object)
                return new List<List<JsonElement>>();
            if (!state.TryGetProperty(key, out var hands))
                return new List<List<JsonElement>>();
            if (hands.ValueKind != JsonValueKind.Array)
                return new List<List<JsonElement>>();
            var list = new List<List<JsonElement>>();
            foreach (var hand in hands.EnumerateArray())
            {
                if (hand.ValueKind == JsonValueKind.Array)
                    list.Add(hand.EnumerateArray().ToList());
                else if (hand.ValueKind == JsonValueKind.Object)
                    list.Add(new List<JsonElement> { hand });
            }
            return list;
        }
        catch
        {
            return new List<List<JsonElement>>();
        }
    }

    private static List<string> GetStringList(JsonElement state, string key)
    {
        try
        {
            if (state.ValueKind != JsonValueKind.Object)
                return new List<string>();
            if (!state.TryGetProperty(key, out var list))
                return new List<string>();
            if (list.ValueKind != JsonValueKind.Array)
                return new List<string>();
            return list.EnumerateArray()
                .Where(item => item.ValueKind == JsonValueKind.String)
                .Select(item => item.GetString() ?? "")
                .ToList();
        }
        catch
        {
            return new List<string>();
        }
    }

    private static List<int> GetIntList(JsonElement state, string key)
    {
        try
        {
            if (state.ValueKind != JsonValueKind.Object)
                return new List<int>();
            if (!state.TryGetProperty(key, out var list))
                return new List<int>();
            if (list.ValueKind != JsonValueKind.Array)
                return new List<int>();
            var values = new List<int>();
            foreach (var item in list.EnumerateArray())
            {
                if (item.ValueKind == JsonValueKind.Number && item.TryGetInt32(out var val))
                    values.Add(val);
            }
            return values;
        }
        catch
        {
            return new List<int>();
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
            try
            {
                if (card.TryGetProperty("image", out var imgEl) && imgEl.ValueKind == JsonValueKind.String)
                    img = ResolveCardImageUrl(imgEl.GetString());
            }
            catch (ArgumentOutOfRangeException)
            {
                img = "";
            }
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
        var baseUrl = Plugin.Config.BingoApiBaseUrl ?? "https://rites.thebigtree.life";
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
        var baseUrl = Plugin.Config.BingoApiBaseUrl ?? "https://rites.thebigtree.life";
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

    private async Task Cardgames_CreateSession(bool draft)
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
            var pot = _cardgamesPot;
            var currency = _cardgamesCurrency;
            var deckId = _cardgamesSelectedDeckId;
            var backgroundUrl = _cardgamesBackgroundUrl;

            if (_currentVenue != null)
            {
                if (pot <= 0 && _currentVenue.MinimalSpend.HasValue)
                    pot = _currentVenue.MinimalSpend.Value;
                if (string.IsNullOrWhiteSpace(currency) && !string.IsNullOrWhiteSpace(_currentVenue.CurrencyName))
                    currency = _currentVenue.CurrencyName;
                if (string.IsNullOrWhiteSpace(deckId) && !string.IsNullOrWhiteSpace(_currentVenue.DeckId))
                    deckId = _currentVenue.DeckId;

                if (_currentVenue.Metadata?.GameBackgrounds != null
                    && _currentVenue.Metadata.GameBackgrounds.TryGetValue(_cardgamesGameId, out var venueGameBg)
                    && !string.IsNullOrWhiteSpace(venueGameBg))
                {
                    backgroundUrl = venueGameBg;
                }
                else if (string.IsNullOrWhiteSpace(backgroundUrl) && !string.IsNullOrWhiteSpace(_currentVenue.BackgroundImage))
                {
                    backgroundUrl = _currentVenue.BackgroundImage;
                }
            }

            var resp = await _cardgamesApi!.CreateSessionAsync(
                _cardgamesGameId,
                pot,
                deckId,
                currency,
                backgroundUrl,
                draft
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
            RequestSessionsRefresh(true);
            if (_cardgamesOpenAfterCreate)
            {
                _cardgamesOpenAfterCreate = false;
                _cardgamesSelectedSession = s;
                _view = View.Cardgames;
                _controlSurfaceOpen = true;
                _topView = TopView.Sessions;
                _cardgamesPendingExpandAfterCreate = true;
                _ = Cardgames_LoadState();
            }
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
            RequestSessionsRefresh(true);
        }
        catch (Exception ex)
        {
            _cardgamesStatus = $"Clone failed: {ex.Message}";
        }
    }

    private async Task Cardgames_CloneAndFinishSelected()
    {
        if (_cardgamesSelectedSession is null)
            return;
        await Cardgames_CloneSelected();
        await Cardgames_FinishSelected();
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
            RequestSessionsRefresh(true);
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
            RequestSessionsRefresh(true);
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

    private async Task Cardgames_CloseSession(CardgameSession session)
    {
        Cardgames_EnsureClient();
        _cardgamesStatus = "Closing session.";
        try
        {
            if (string.Equals(session.status, "live", StringComparison.OrdinalIgnoreCase))
            {
                var resp = await _cardgamesApi!.FinishSessionAsync(session.game_id, session.session_id, session.priestess_token);
                if (!resp.ok)
                {
                    _cardgamesStatus = resp.error ?? "Close failed.";
                    return;
                }
            }
            else
            {
                var resp = await _cardgamesApi!.DeleteSessionAsync(session.game_id, session.session_id, session.priestess_token);
                if (!resp.ok)
                {
                    _cardgamesStatus = resp.error ?? "Delete failed.";
                    return;
                }
            }
            _cardgamesStatus = "Session closed.";
        }
        catch (Exception ex)
        {
            _cardgamesStatus = $"Close failed: {ex.Message}";
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
            Plugin.Config.BingoApiBaseUrl ?? "https://rites.thebigtree.life",
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
            RequestSessionsRefresh(true);
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
            RequestSessionsRefresh(true);
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
            RequestSessionsRefresh(true);
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

    private async Task Hunt_EndGame(string huntId)
    {
        if (string.IsNullOrWhiteSpace(huntId))
            return;
        Hunt_EnsureClient();
        _huntLoading = true;
        try
        {
            await _huntApi!.EndAsync(huntId);
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
            RequestSessionsRefresh(true);
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
            RequestSessionsRefresh(true);
        }
        catch (Exception ex) { _bingoStatus = $"End failed: {ex.Message}"; }
        finally { _bingoLoading = false; }
    }

    private async Task Bingo_EndGame(string gameId)
    {
        if (string.IsNullOrWhiteSpace(gameId))
            return;
        Bingo_EnsureClient();
        _bingoLoading = true;
        _bingoStatus = "Ending game.";
        try
        {
            await _bingoApi!.EndGameAsync(gameId);
            _bingoStatus = "Game ended.";
            RequestSessionsRefresh(true);
        }
        catch (Exception ex)
        {
            _bingoStatus = $"End failed: {ex.Message}";
        }
        finally
        {
            _bingoLoading = false;
        }
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

    /// <summary>
    /// Executes a chat command in the game. Can be used for any command like /say, /saddlebag, /random, etc.
    /// Must be called on the Framework thread.
    /// </summary>
    private unsafe void ExecuteChatCommand(string cmd)
    {
        var uiModule = UIModule.Instance();
        var shell = uiModule->GetRaptureShellModule();
        var command = new Utf8String();
        command.SetString(cmd);
        shell->ExecuteCommandInner(&command, uiModule);
        command.Dtor();
    }

    private void Bingo_Roll()
    {
        if (_bingoState is null)
        {
            _bingoStatus = "Load a game first.";
            Plugin.Framework.RunOnFrameworkThread(() => Plugin.ChatGui.PrintError("[Forest] Load a game first."));
            return;
        }
        if (_bingoWaitingForRandomRoll)
        {
            _bingoStatus = "Already rolling.";
            return;
        }
        Bingo_EnsureClient();
        _bingoLoading = true;
        _bingoWaitingForRandomRoll = true;
        _bingoStatus = "Rolling...";

        
        _bingoRandomRerollAttempts = 0;
// Execute /random 40 command in-game, result will be parsed from chat
        Plugin.Framework.RunOnFrameworkThread(() => ExecuteChatCommand("/random 40"));
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

    private async Task<bool> TryHandleBingoRandomAsync(string senderText, string messageText)
    {
        try
        {
            // Only accept manual /random results when we are connected to the online Bingo game.
            // Otherwise we'd risk diverging local state from the server state.
            if (!Plugin.Config.BingoConnected || _bingoApi is null || string.IsNullOrWhiteSpace(_bingoGameId) || _bingoState is null || !_bingoState.game.active)
                return false;
                        if (DateTime.UtcNow < _bingoRandomCooldownUntil)
                return false;
            if (string.IsNullOrWhiteSpace(messageText)) return false;
            var lower = messageText.ToLowerInvariant();
            if (!_bingoWaitingForRandomRoll && !lower.Contains("roll") && !lower.Contains("random") && !lower.Contains("lot")) return false;

            var matches = Regex.Matches(messageText, "\\d+");
            if (matches.Count == 0) return false;
            if (!int.TryParse(matches[0].Value, out var rolled)) return false;
            if (rolled < 1 || rolled > 40) return false;

            if (_bingoWaitingForRandomRoll)
            {
                _bingoWaitingForRandomRoll = false;
                var success = await Bingo_HandleRandomResult(rolled);
                if (success)
                    _bingoLoading = false;
                return true;
            }

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

            _ = Bingo_HandleRandomResult(rolled);
            return true;
        }
        catch (Exception ex)
        {
            Plugin.ChatGui.PrintError($"[Forest] Error handling bingo random: {ex.Message}");
            return false;
        }
    }

    private async Task<bool> Bingo_HandleRandomResult(int rolled)
    {
        if (_bingoState is null)
        {
            _bingoStatus = "Load a game first.";
            Plugin.Framework.RunOnFrameworkThread(() => Plugin.ChatGui.PrintError("[Forest] Load a game first."));
            _bingoWaitingForRandomRoll = false;
            _bingoLoading = false;
            return false;
        }
        if (!_bingoState.game.started)
        {
            _bingoStatus = "Game not started.";
            Plugin.Framework.RunOnFrameworkThread(() => Plugin.ChatGui.PrintError("[Forest] Game not started."));
            _bingoWaitingForRandomRoll = false;
            _bingoLoading = false;
            return false;
        }
        if (rolled < 1 || rolled > BingoRandomMax) 
        {
            _bingoWaitingForRandomRoll = false;
            _bingoLoading = false;
            return false;
        }

        var called = new HashSet<int>(_bingoState.game.called ?? Array.Empty<int>());
        if (called.Count >= BingoRandomMax)
        {
            _bingoStatus = "All numbers called.";
            Plugin.Framework.RunOnFrameworkThread(() => Plugin.ChatGui.PrintError("[Forest] All numbers called."));
            _bingoWaitingForRandomRoll = false;
            _bingoLoading = false;
            return false;
        }

        if (called.Contains(rolled))
        {
            // Duplicate roll: try again up to 5 times, then stop.
            _bingoRandomRerollAttempts++;
            if (_bingoRandomRerollAttempts <= 5)
            {
                _bingoStatus = $"Duplicate ({rolled}) — retrying ({_bingoRandomRerollAttempts}/5)...";
                // Duplicate roll: wait 1s and trigger another roll; result will be parsed from chat.
                _bingoWaitingForRandomRoll = true;
                _bingoLoading = true;
                await Task.Delay(1000);
                Plugin.Framework.RunOnFrameworkThread(() => ExecuteChatCommand("/random 40"));
                return false;
            }

            _bingoStatus = $"Rolled a duplicate number {rolled} too many times. Stopping.";
            _bingoWaitingForRandomRoll = false;
            _bingoLoading = false;
            return false;
        }

        try
        {
            var res = await _bingoApi!.CallNumberAsync(_bingoState.game.game_id, rolled);
            var newCalled = res.called ?? _bingoState.game.called ?? Array.Empty<int>();
            _bingoState = _bingoState with { game = _bingoState.game with { called = newCalled, last_called = rolled } };
            _bingoStatus = $"Rolled {rolled}.";
            Bingo_AddAction($"Called {FormatBingoCall(rolled)}");
            if (_bingoAnnounceCalls)
                Plugin.Framework.RunOnFrameworkThread(() => Plugin.ChatGui.Print($"[Forest] Called number {rolled}."));
            _bingoRandomCooldownUntil = DateTime.UtcNow.AddSeconds(5);
            _bingoWaitingForRandomRoll = false;
            _bingoLoading = false;
            return true; // success
        }
        catch (Exception ex)
        {
            _bingoStatus = $"Failed: {ex.Message}";
            Plugin.Framework.RunOnFrameworkThread(() => Plugin.ChatGui.PrintError($"[Forest] Call failed: {ex.Message}"));
            _bingoWaitingForRandomRoll = false;
            _bingoLoading = false;
            return false;
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
                var baseUrl = (Plugin.Config.BingoApiBaseUrl ?? "https://rites.thebigtree.life").TrimEnd('/');
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