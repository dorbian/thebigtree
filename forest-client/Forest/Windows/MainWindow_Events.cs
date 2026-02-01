using Dalamud.Bindings.ImGui;
using Dalamud.Interface.Utility.Raii;
using Forest.Features.Events;
using Forest.Features.Venues;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Numerics;
using System.Threading.Tasks;

namespace Forest.Windows;

public partial class MainWindow
{
    // Events state
    private List<EventInfo> _events = new();
    private EventInfo? _selectedEvent;
    private List<EventPlayer> _eventPlayers = new();
    private List<EventGameSession> _eventGames = new();
    private bool _eventsLoading = false;
    private bool _eventPlayersLoading = false;
    private string _eventStatus = "";
    private DateTime _eventsLastRefresh = DateTime.MinValue;
    
    // Create event form
    private string _eventCreateCode = "";
    private string _eventCreateName = "";
    private bool _eventCreateWalletEnabled = true;
    private string _eventCreateEnabledGames = "blackjack,slots";
    private int _eventCreateJoinBonus = 1000;

    // Venue state
    private VenueMembership? _currentVenue = null;
    private List<Venue> _availableVenues = new();
    private bool _venueLoading = false;
    private DateTime _venueLastFetch = DateTime.MinValue;

    private async Task Events_LoadList()
    {
        if (Plugin.EventsApi == null)
        {
            _eventStatus = "Events API not initialized";
            return;
        }

        _eventsLoading = true;
        _eventStatus = "Loading events...";
        try
        {
            var venueId = _currentVenue?.VenueId;
            _events = await Plugin.EventsApi.ListEventsAsync(venueId, includeEnded: false);
            _eventsLastRefresh = DateTime.UtcNow;
            _eventStatus = $"Loaded {_events.Count} event(s)";
        }
        catch (Exception ex)
        {
            _eventStatus = $"Failed: {ex.Message}";
            Plugin.Log.Error(ex, "Events_LoadList failed");
        }
        finally
        {
            _eventsLoading = false;
        }
    }

    private async Task Events_Create()
    {
        if (Plugin.EventsApi == null || string.IsNullOrWhiteSpace(_eventCreateName))
            return;

        _eventsLoading = true;
        try
        {
            var enabledGames = _eventCreateEnabledGames
                .Split(',')
                .Select(g => g.Trim().ToLowerInvariant())
                .Where(g => !string.IsNullOrWhiteSpace(g))
                .ToList();

            var request = new CreateEventRequest
            {
                Code = string.IsNullOrWhiteSpace(_eventCreateCode) ? null : _eventCreateCode,
                Name = _eventCreateName,
                VenueId = _currentVenue?.VenueId,
                WalletEnabled = _eventCreateWalletEnabled,
                CurrencyName = _currentVenue?.CurrencyName,
                EnabledGames = enabledGames.Count > 0 ? enabledGames : null,
                JoinWalletAmount = _eventCreateWalletEnabled ? _eventCreateJoinBonus : null
            };

            var created = await Plugin.EventsApi.CreateEventAsync(request);
            if (created != null)
            {
                _eventStatus = $"Created event: {created.Name} ({created.Code})";
                Plugin.Config.LastEventCode = created.Code;
                Plugin.Config.Save();
                await Events_LoadList();
                
                // Clear form
                _eventCreateCode = "";
                _eventCreateName = "";
            }
            else
            {
                _eventStatus = "Failed to create event";
            }
        }
        catch (Exception ex)
        {
            _eventStatus = $"Failed: {ex.Message}";
            Plugin.Log.Error(ex, "Events_Create failed");
        }
        finally
        {
            _eventsLoading = false;
        }
    }

    private async Task Events_End(int eventId)
    {
        if (Plugin.EventsApi == null)
            return;

        _eventsLoading = true;
        try
        {
            var success = await Plugin.EventsApi.EndEventAsync(eventId);
            if (success)
            {
                _eventStatus = "Event ended";
                await Events_LoadList();
            }
            else
            {
                _eventStatus = "Failed to end event";
            }
        }
        catch (Exception ex)
        {
            _eventStatus = $"Failed: {ex.Message}";
            Plugin.Log.Error(ex, "Events_End failed");
        }
        finally
        {
            _eventsLoading = false;
        }
    }

    private async Task Events_LoadPlayers(EventInfo ev)
    {
        if (Plugin.EventsApi == null)
            return;

        _eventPlayersLoading = true;
        try
        {
            _eventPlayers = await Plugin.EventsApi.GetEventPlayersAsync(ev.Id);
        }
        catch (Exception ex)
        {
            Plugin.Log.Error(ex, "Events_LoadPlayers failed");
            _eventPlayers.Clear();
        }
        finally
        {
            _eventPlayersLoading = false;
        }
    }

    private async Task Events_LoadGames(EventInfo ev)
    {
        if (Plugin.EventsApi == null)
            return;

        try
        {
            _eventGames = await Plugin.EventsApi.GetEventGamesAsync(ev.Code);
        }
        catch (Exception ex)
        {
            Plugin.Log.Error(ex, "Events_LoadGames failed");
            _eventGames.Clear();
        }
    }

    private async Task Events_CreateGame(EventInfo ev, string gameId)
    {
        if (Plugin.EventsApi == null)
            return;

        try
        {
            var result = await Plugin.EventsApi.CreateEventGameAsync(ev.Code, gameId);
            if (result.Ok)
            {
                _eventStatus = $"Created {gameId} for {ev.Code}";
                await Events_LoadGames(ev);
                RequestSessionsRefresh(true);
            }
            else
            {
                _eventStatus = result.Error ?? "Failed to create event game";
            }
        }
        catch (Exception ex)
        {
            _eventStatus = $"Failed: {ex.Message}";
            Plugin.Log.Error(ex, "Events_CreateGame failed");
        }
    }

    private async Task Venue_LoadCurrent()
    {
        if (Plugin.VenuesApi == null)
            return;

        _venueLoading = true;
        try
        {
            var venues = await Plugin.VenuesApi.ListVenuesAsync();
            _venueLastFetch = DateTime.UtcNow;
            _availableVenues = venues;
            if (Plugin.Config.CurrentVenueId.HasValue)
            {
                var venue = venues.FirstOrDefault(v => v.Id == Plugin.Config.CurrentVenueId.Value);
                _currentVenue = venue != null ? MapVenueToMembership(venue) : null;
            }
        }
        catch (Exception ex)
        {
            Plugin.Log.Error(ex, "Venue_LoadCurrent failed");
        }
        finally
        {
            _venueLoading = false;
        }
    }

    private static VenueMembership MapVenueToMembership(Venue venue)
    {
        return new VenueMembership
        {
            VenueId = venue.Id,
            VenueName = venue.Name,
            CurrencyName = venue.CurrencyName,
            MinimalSpend = venue.MinimalSpend,
            BackgroundImage = venue.BackgroundImage,
            DeckId = venue.DeckId,
            Metadata = venue.Metadata
        };
    }

    private async Task Venue_LoadAvailable()
    {
        if (Plugin.VenuesApi == null)
            return;

        _venueLoading = true;
        try
        {
            _availableVenues = await Plugin.VenuesApi.ListVenuesAsync();
        }
        catch (Exception ex)
        {
            Plugin.Log.Error(ex, "Venue_LoadAvailable failed");
            _availableVenues.Clear();
        }
        finally
        {
            _venueLoading = false;
        }
    }

    private async Task Venue_Assign(int venueId)
    {
        if (Plugin.VenuesApi == null)
            return;

        _venueLoading = true;
        try
        {
            var success = await Plugin.VenuesApi.AssignVenueAsync(venueId);
            if (success)
            {
                await Venue_LoadCurrent();
            }
        }
        catch (Exception ex)
        {
            Plugin.Log.Error(ex, "Venue_Assign failed");
        }
        finally
        {
            _venueLoading = false;
        }
    }

    private void DrawEventsPanel()
    {
        ImGui.TextUnformatted("Events & Venue Management");
        ImGui.Separator();

        // Venue info section
        if (_currentVenue != null)
        {
            ImGui.TextColored(new Vector4(0.5f, 1f, 0.6f, 1f), $"Venue: {_currentVenue.VenueName}");
            if (_currentVenue.CurrencyName != null)
                ImGui.TextDisabled($"Currency: {_currentVenue.CurrencyName}");
            if (_currentVenue.MinimalSpend.HasValue)
                ImGui.TextDisabled($"Minimal spend: {_currentVenue.MinimalSpend.Value:N0}");
        }
        else
        {
            ImGui.TextDisabled("No venue assigned");
            if (ImGui.Button("Load Venue"))
                _ = Venue_LoadCurrent();
        }

        ImGui.Spacing();
        ImGui.Separator();

        // Events list
        ImGui.TextUnformatted("Active Events");
        ImGui.SameLine();
        if (ImGui.SmallButton("Refresh"))
            _ = Events_LoadList();

        if (!string.IsNullOrWhiteSpace(_eventStatus))
            ImGui.TextDisabled(_eventStatus);

        if (_eventsLoading)
        {
            ImGui.TextDisabled("Loading...");
        }
        else if (_events.Count == 0)
        {
            ImGui.TextDisabled("No events found.");
        }
        else
        {
            if (ImGui.BeginTable("EventsTable", 4, ImGuiTableFlags.RowBg | ImGuiTableFlags.BordersInnerV))
            {
                ImGui.TableSetupColumn("Code", ImGuiTableColumnFlags.WidthFixed, 80f);
                ImGui.TableSetupColumn("Name", ImGuiTableColumnFlags.WidthStretch);
                ImGui.TableSetupColumn("Status", ImGuiTableColumnFlags.WidthFixed, 60f);
                ImGui.TableSetupColumn("Actions", ImGuiTableColumnFlags.WidthFixed, 120f);
                ImGui.TableHeadersRow();

                foreach (var ev in _events)
                {
                    ImGui.TableNextRow();
                    ImGui.TableNextColumn();
                    ImGui.TextUnformatted(ev.Code);
                    
                    ImGui.TableNextColumn();
                    bool isSelected = _selectedEvent?.Id == ev.Id;
                    if (ImGui.Selectable(ev.Name, isSelected, ImGuiSelectableFlags.SpanAllColumns))
                    {
                        _selectedEvent = ev;
                        _ = Events_LoadPlayers(ev);
                        _ = Events_LoadGames(ev);
                    }
                    
                    ImGui.TableNextColumn();
                    ImGui.TextUnformatted(ev.Status);
                    
                    ImGui.TableNextColumn();
                    if (ImGui.SmallButton($"End##{ev.Id}"))
                        _ = Events_End(ev.Id);
                    ImGui.SameLine();
                    if (ImGui.SmallButton($"Copy##{ev.Id}"))
                    {
                        var url = $"{Plugin.Config.BingoApiBaseUrl?.TrimEnd('/')}/events/{ev.Code}";
                        ImGui.SetClipboardText(url);
                    }
                }

                ImGui.EndTable();
            }
        }

        // Selected event details
        if (_selectedEvent != null)
        {
            ImGui.Spacing();
            ImGui.Separator();
            ImGui.TextUnformatted($"Event: {_selectedEvent.Name} ({_selectedEvent.Code})");
            ImGui.Spacing();
            ImGui.TextUnformatted("Create game");
            using (var dis = ImRaii.Disabled(_eventsLoading))
            {
                if (ImGui.SmallButton("Blackjack"))
                    _ = Events_CreateGame(_selectedEvent, "blackjack");
                ImGui.SameLine();
                if (ImGui.SmallButton("Slots"))
                    _ = Events_CreateGame(_selectedEvent, "slots");
            }
            
            if (ImGui.BeginTabBar("EventDetailsTabs"))
            {
                if (ImGui.BeginTabItem("Players"))
                {
                    if (_eventPlayersLoading)
                    {
                        ImGui.TextDisabled("Loading players...");
                    }
                    else if (_eventPlayers.Count == 0)
                    {
                        ImGui.TextDisabled("No players joined yet.");
                    }
                    else
                    {
                        ImGui.TextUnformatted($"{_eventPlayers.Count} player(s)");
                        foreach (var player in _eventPlayers)
                        {
                            ImGui.BulletText(player.XivUsername);
                            if (player.WalletBalance.HasValue)
                            {
                                ImGui.SameLine();
                                ImGui.TextDisabled($"({player.WalletBalance.Value:N0})");
                            }
                        }
                    }
                    ImGui.EndTabItem();
                }

                if (ImGui.BeginTabItem("Games"))
                {
                    if (_eventGames.Count == 0)
                    {
                        ImGui.TextDisabled("No games in this event.");
                    }
                    else
                    {
                        foreach (var game in _eventGames)
                        {
                            var status = game.Active ? "Active" : "Ended";
                            ImGui.BulletText($"{game.GameId} ({game.JoinCode}) - {status}");
                        }
                    }
                    ImGui.EndTabItem();
                }

                ImGui.EndTabBar();
            }
        }

        // Create event form
        ImGui.Spacing();
        ImGui.Separator();
        if (ImGui.CollapsingHeader("Create New Event"))
        {
            ImGui.InputText("Code (optional)", ref _eventCreateCode, 32);
            ImGui.InputText("Name", ref _eventCreateName, 128);
            ImGui.Checkbox("Enable wallet", ref _eventCreateWalletEnabled);
            
            if (_eventCreateWalletEnabled)
            {
                ImGui.InputInt("Join bonus", ref _eventCreateJoinBonus);
                if (_eventCreateJoinBonus < 0)
                    _eventCreateJoinBonus = 0;
            }
            
            ImGui.InputText("Enabled games (csv)", ref _eventCreateEnabledGames, 256);
            
            using (var dis = ImRaii.Disabled(string.IsNullOrWhiteSpace(_eventCreateName) || _eventsLoading))
            {
                if (ImGui.Button("Create Event"))
                    _ = Events_Create();
            }
        }
    }
}
