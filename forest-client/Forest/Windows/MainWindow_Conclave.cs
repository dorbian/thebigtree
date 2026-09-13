using Dalamud.Bindings.ImGui;
using Forest.Features.Conclave;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Numerics;
using System.Threading.Tasks;

namespace Forest.Windows;

public partial class MainWindow
{
    private List<ConclaveSession> _conclaveSessions = new();
    private ConclaveSession? _conclaveSelected;
    private bool _conclaveLoading;
    private string _conclaveStatus = "";
    private DateTime _conclaveLastRefresh = DateTime.MinValue;

    private async Task Conclave_LoadSessions()
    {
        if (Plugin.ConclaveApi == null)
        {
            _conclaveStatus = "Conclave API is not initialized.";
            return;
        }
        if (_conclaveLoading)
            return;
        _conclaveLoading = true;
        _conclaveStatus = "Loading Discord Conclaves...";
        try
        {
            var response = await Plugin.ConclaveApi.ListAsync(includeEnded: false);
            if (!response.ok)
            {
                _conclaveStatus = response.error ?? "The server rejected the request.";
                return;
            }
            _conclaveSessions = response.sessions ?? new List<ConclaveSession>();
            if (_conclaveSelected?.game_id is not null)
            {
                _conclaveSelected = _conclaveSessions.FirstOrDefault(
                    x => string.Equals(x.game_id, _conclaveSelected.game_id, StringComparison.OrdinalIgnoreCase));
            }
            _conclaveSelected ??= _conclaveSessions.FirstOrDefault();
            _conclaveLastRefresh = DateTime.UtcNow;
            _conclaveStatus = $"Loaded {_conclaveSessions.Count} active Conclave(s).";
        }
        catch (Exception ex)
        {
            _conclaveStatus = $"Load failed: {ex.Message}";
            Plugin.Log.Error(ex, "Conclave_LoadSessions failed");
        }
        finally
        {
            _conclaveLoading = false;
        }
    }

    private async Task Conclave_Action(string action)
    {
        var session = _conclaveSelected;
        if (Plugin.ConclaveApi == null || string.IsNullOrWhiteSpace(session?.game_id))
            return;
        _conclaveLoading = true;
        try
        {
            ConclaveSessionResponse response = action switch
            {
                "start" => await Plugin.ConclaveApi.StartAsync(session.game_id),
                "advance" => await Plugin.ConclaveApi.AdvanceAsync(session.game_id),
                "end" => await Plugin.ConclaveApi.EndAsync(session.game_id),
                _ => new ConclaveSessionResponse { ok = false, error = "Unknown action" }
            };
            if (!response.ok)
            {
                _conclaveStatus = response.error ?? "Action rejected by server.";
                return;
            }
            _conclaveSelected = response.session;
            if (response.session is not null)
            {
                var index = _conclaveSessions.FindIndex(x =>
                    string.Equals(x.game_id, response.session.game_id, StringComparison.OrdinalIgnoreCase));
                if (action == "end" || string.Equals(response.session.phase, "ended", StringComparison.OrdinalIgnoreCase))
                {
                    if (index >= 0)
                        _conclaveSessions.RemoveAt(index);
                }
                else if (index >= 0)
                {
                    _conclaveSessions[index] = response.session;
                }
                else
                {
                    _conclaveSessions.Add(response.session);
                }
            }
            _conclaveStatus = action switch
            {
                "start" => "Conclave started in Discord.",
                "advance" => $"Advanced to {response.session?.phase ?? "next phase"}.",
                "end" => "Conclave ended.",
                _ => "Updated."
            };
            if (action == "end")
                _conclaveSelected = _conclaveSessions.FirstOrDefault();
        }
        catch (Exception ex)
        {
            _conclaveStatus = $"Action failed: {ex.Message}";
            Plugin.Log.Error(ex, $"Conclave action {action} failed");
        }
        finally
        {
            _conclaveLoading = false;
        }
    }

    private static string ConclaveGuidance(string? phase)
    {
        return phase switch
        {
            "lobby" => "Gather players in Discord, then start when the circle is ready.",
            "night" => "Private choices happen in Discord. Advance when the host is satisfied with readiness.",
            "day" => "Allow the council to discuss the public night result, then advance to nominations.",
            "nomination" => "Players nominate or abstain in Discord. Advance when the council is ready.",
            "trial" => "Give the accused time to defend themselves before moving to judgement.",
            "judgement" => "Private verdicts happen in Discord. Advance to resolve the judgement.",
            "ended" => "The final public result remains available in Discord and the web console.",
            _ => "Discord remains the player surface; Forest exposes host-safe state only."
        };
    }

    private static string ConclavePhaseLabel(string? phase)
    {
        return phase switch
        {
            "lobby" => "Gathering",
            "night" => "Night",
            "day" => "Dawn Council",
            "nomination" => "Nominations",
            "trial" => "Trial / Defence",
            "judgement" => "Judgement",
            "ended" => "Ended",
            _ => phase ?? "Unknown"
        };
    }

    private void DrawConclavePanel()
    {
        if (!_conclaveLoading && (DateTime.UtcNow - _conclaveLastRefresh).TotalSeconds >= 10)
            _ = Conclave_LoadSessions();

        ImGui.TextUnformatted("Verdant Conclave · Discord Host Console");
        ImGui.TextDisabled("Players, roles, actions and voting stay in the dedicated Discord channel.");
        ImGui.TextDisabled("Forest exposes host controls only and never reveals living secret roles.");
        ImGui.Separator();

        if (ImGui.Button("Refresh Conclaves"))
            _ = Conclave_LoadSessions();
        ImGui.SameLine();
        if (_conclaveLastRefresh != DateTime.MinValue)
            ImGui.TextDisabled($"Last refresh: {_conclaveLastRefresh.ToLocalTime():HH:mm:ss}");

        if (!string.IsNullOrWhiteSpace(_conclaveStatus))
        {
            ImGui.Spacing();
            ImGui.TextWrapped(_conclaveStatus);
        }

        ImGui.Spacing();
        if (_conclaveLoading)
        {
            ImGui.TextDisabled("Working...");
            return;
        }

        if (_conclaveSessions.Count == 0)
        {
            ImGui.TextDisabled("No active Discord Conclave found.");
            ImGui.TextWrapped("Create one with /conclave-create in Discord. By default TheBigTree creates a dedicated channel and locks all game actions to it.");
            return;
        }

        ImGui.BeginChild("ConclaveSessions", new Vector2(250, 0), true);
        foreach (var session in _conclaveSessions)
        {
            var id = session.game_id ?? "unknown";
            var title = string.IsNullOrWhiteSpace(session.title) ? id : session.title;
            var selected = string.Equals(_conclaveSelected?.game_id, id, StringComparison.OrdinalIgnoreCase);
            if (ImGui.Selectable($"{title}##{id}", selected))
                _conclaveSelected = session;
            ImGui.TextDisabled($"{ConclavePhaseLabel(session.phase)} · #{session.channel_id}");
        }
        ImGui.EndChild();

        ImGui.SameLine();
        ImGui.BeginGroup();
        var current = _conclaveSelected;
        if (current is null)
        {
            ImGui.TextDisabled("Select a Conclave.");
            ImGui.EndGroup();
            return;
        }

        ImGui.TextUnformatted(current.title ?? current.game_id ?? "Verdant Conclave");
        ImGui.TextDisabled(current.game_id ?? "");
        ImGui.Separator();
        ImGui.Text($"Phase: {ConclavePhaseLabel(current.phase)}");
        ImGui.TextWrapped(ConclaveGuidance(current.phase));
        ImGui.Text($"Discord channel ID: {current.channel_id}");
        if (current.night > 0) ImGui.Text($"Night: {current.night}");
        if (current.day > 0) ImGui.Text($"Day: {current.day}");

        var players = current.players ?? new List<ConclavePlayer>();
        var living = players.Count(p => p.alive);
        ImGui.Text($"Players: {living}/{players.Count} living");
        if (current.readiness?.required > 0)
            ImGui.Text($"Choices ready: {current.readiness.ready}/{current.readiness.required}");
        if (current.role_roster is { Count: > 0 })
        {
            var roster = string.Join(", ", current.role_roster.Select(r => $"{r.name ?? r.role_id} ×{r.count}"));
            ImGui.TextWrapped($"Role roster: {roster}");
        }

        ImGui.Spacing();
        if (current.phase == "lobby")
        {
            if (ImGui.Button("Start in Discord"))
                _ = Conclave_Action("start");
        }
        else if (current.phase != "ended")
        {
            if (ImGui.Button("Advance phase"))
                _ = Conclave_Action("advance");
        }
        if (current.phase != "ended")
        {
            ImGui.SameLine();
            if (ImGui.Button("End Conclave"))
                _ = Conclave_Action("end");
        }

        ImGui.Spacing();
        ImGui.Separator();
        ImGui.TextUnformatted("Public player state");
        foreach (var p in players)
        {
            var onTrial = p.alive && current.on_trial.HasValue && current.on_trial.Value == p.user_id;
            var state = p.alive ? (onTrial ? "On trial" : "Living") : "Fallen";
            var role = !p.alive && !string.IsNullOrWhiteSpace(p.role) ? $" · {p.role}" : "";
            ImGui.BulletText($"{p.display_name ?? p.user_id.ToString()} · {state}{role}");
        }

        if (current.public_events is { Count: > 0 })
        {
            ImGui.Spacing();
            ImGui.TextUnformatted("Latest public events");
            foreach (var line in current.public_events.TakeLast(4))
                ImGui.BulletText(line);
        }
        ImGui.EndGroup();
    }
}
