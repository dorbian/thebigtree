using System;
using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Forest.Features.Events;

public sealed class EventInfo
{
    [JsonPropertyName("id")]
    public int Id { get; set; }

    [JsonPropertyName("code")]
    public string Code { get; set; } = string.Empty;

    [JsonPropertyName("name")]
    public string Name { get; set; } = string.Empty;

    [JsonPropertyName("status")]
    public string Status { get; set; } = "active";

    [JsonPropertyName("venue_id")]
    public int? VenueId { get; set; }

    [JsonPropertyName("venue_name")]
    public string? VenueName { get; set; }

    [JsonPropertyName("wallet_enabled")]
    public bool WalletEnabled { get; set; }

    [JsonPropertyName("currency_name")]
    public string? CurrencyName { get; set; }

    [JsonPropertyName("created_at")]
    public DateTime? CreatedAt { get; set; }

    [JsonPropertyName("metadata")]
    public EventMetadata? Metadata { get; set; }
}

public sealed class EventMetadata
{
    [JsonPropertyName("enabled_games")]
    public List<string>? EnabledGames { get; set; }

    [JsonPropertyName("join_wallet_amount")]
    public int? JoinWalletAmount { get; set; }

    [JsonPropertyName("background_url")]
    public string? BackgroundUrl { get; set; }
}

public sealed class EventPlayer
{
    [JsonPropertyName("user_id")]
    public int? UserId { get; set; }

    [JsonPropertyName("xiv_username")]
    public string XivUsername { get; set; } = string.Empty;

    [JsonPropertyName("joined_at")]
    public DateTime? JoinedAt { get; set; }

    [JsonPropertyName("wallet_balance")]
    public int? WalletBalance { get; set; }
}

public sealed class EventGameSession
{
    [JsonPropertyName("game_id")]
    public string GameId { get; set; } = string.Empty;

    [JsonPropertyName("join_code")]
    public string JoinCode { get; set; } = string.Empty;

    [JsonPropertyName("module")]
    public string Module { get; set; } = string.Empty;

    [JsonPropertyName("type")]
    public string Type { get; set; } = string.Empty;

    [JsonPropertyName("title")]
    public string? Title { get; set; }

    [JsonPropertyName("join_url")]
    public string? JoinUrl { get; set; }

    [JsonPropertyName("currency")]
    public string? Currency { get; set; }

    [JsonPropertyName("active")]
    public bool Active { get; set; }
}

public sealed class ListEventsResponse
{
    [JsonPropertyName("ok")]
    public bool Ok { get; set; }

    [JsonPropertyName("events")]
    public List<EventInfo> Events { get; set; } = new();
}

public sealed class EventInfoResponse
{
    [JsonPropertyName("ok")]
    public bool Ok { get; set; }

    [JsonPropertyName("event")]
    public EventInfo? Event { get; set; }
}

public sealed class EventPlayersResponse
{
    [JsonPropertyName("ok")]
    public bool Ok { get; set; }

    [JsonPropertyName("event_id")]
    public int EventId { get; set; }

    [JsonPropertyName("players")]
    public List<EventPlayer> Players { get; set; } = new();
}

public sealed class EventGamesResponse
{
    [JsonPropertyName("ok")]
    public bool Ok { get; set; }

    [JsonPropertyName("event")]
    public EventInfo? Event { get; set; }

    [JsonPropertyName("games")]
    public List<EventGameSession> Games { get; set; } = new();
}

public sealed class EventGameCreateResponse
{
    [JsonPropertyName("ok")]
    public bool Ok { get; set; }

    [JsonPropertyName("join_url")]
    public string? JoinUrl { get; set; }

    [JsonPropertyName("error")]
    public string? Error { get; set; }
}

public sealed class CreateEventRequest
{
    [JsonPropertyName("code")]
    public string? Code { get; set; }

    [JsonPropertyName("name")]
    public string Name { get; set; } = string.Empty;

    [JsonPropertyName("venue_id")]
    public int? VenueId { get; set; }

    [JsonPropertyName("wallet_enabled")]
    public bool WalletEnabled { get; set; }

    [JsonPropertyName("currency_name")]
    public string? CurrencyName { get; set; }

    [JsonPropertyName("enabled_games")]
    public List<string>? EnabledGames { get; set; }

    [JsonPropertyName("join_wallet_amount")]
    public int? JoinWalletAmount { get; set; }
}
