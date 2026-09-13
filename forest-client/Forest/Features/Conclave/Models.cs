using System.Collections.Generic;

namespace Forest.Features.Conclave;

public sealed class ConclavePlayer
{
    public long user_id { get; set; }
    public string? display_name { get; set; }
    public bool alive { get; set; }
    // Populated for revealed dead roles and for all players after the game ends.
    public string? role { get; set; }
}


public sealed class ConclaveRoleRosterEntry
{
    public string? role_id { get; set; }
    public string? name { get; set; }
    public string? faction { get; set; }
    public int count { get; set; }
}

public sealed class ConclaveReadiness
{
    public int ready { get; set; }
    public int required { get; set; }
}

public sealed class ConclaveSession
{
    public int version { get; set; }
    public string? game_id { get; set; }
    public string? title { get; set; }
    public long guild_id { get; set; }
    public long channel_id { get; set; }
    public long host_user_id { get; set; }
    public long? panel_message_id { get; set; }
    public string? phase { get; set; }
    public int night { get; set; }
    public int day { get; set; }
    public string? winner { get; set; }
    public string? ended_reason { get; set; }
    public long? on_trial { get; set; }
    public List<string>? public_events { get; set; }
    public List<ConclaveRoleRosterEntry>? role_roster { get; set; }
    public List<ConclavePlayer>? players { get; set; }
    public ConclaveReadiness? readiness { get; set; }
}

public sealed class ConclaveSessionsResponse
{
    public bool ok { get; set; }
    public string? error { get; set; }
    public List<ConclaveSession>? sessions { get; set; }
}

public sealed class ConclaveSessionResponse
{
    public bool ok { get; set; }
    public string? error { get; set; }
    public string? code { get; set; }
    public ConclaveSession? session { get; set; }
}
