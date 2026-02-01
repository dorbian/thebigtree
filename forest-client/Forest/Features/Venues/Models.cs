using System;
using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Forest.Features.Venues;

public sealed class Venue
{
    [JsonPropertyName("id")]
    public int Id { get; set; }

    [JsonPropertyName("name")]
    public string Name { get; set; } = string.Empty;

    [JsonPropertyName("currency_name")]
    public string? CurrencyName { get; set; }

    [JsonPropertyName("minimal_spend")]
    public int? MinimalSpend { get; set; }

    [JsonPropertyName("background_image")]
    public string? BackgroundImage { get; set; }

    [JsonPropertyName("deck_id")]
    public string? DeckId { get; set; }

    [JsonPropertyName("metadata")]
    public VenueMetadata? Metadata { get; set; }

    [JsonPropertyName("created_at")]
    public DateTime? CreatedAt { get; set; }
}

public sealed class VenueMetadata
{
    [JsonPropertyName("admin_discord_ids")]
    public List<string>? AdminDiscordIds { get; set; }

    [JsonPropertyName("game_backgrounds")]
    public Dictionary<string, string>? GameBackgrounds { get; set; }
}

public sealed class VenueMembership
{
    [JsonPropertyName("venue_id")]
    public int? VenueId { get; set; }

    [JsonPropertyName("venue_name")]
    public string? VenueName { get; set; }

    [JsonPropertyName("role")]
    public string? Role { get; set; }

    [JsonPropertyName("currency_name")]
    public string? CurrencyName { get; set; }

    [JsonPropertyName("minimal_spend")]
    public int? MinimalSpend { get; set; }

    [JsonPropertyName("background_image")]
    public string? BackgroundImage { get; set; }

    [JsonPropertyName("deck_id")]
    public string? DeckId { get; set; }

    [JsonPropertyName("metadata")]
    public VenueMetadata? Metadata { get; set; }
}

public sealed class ListVenuesResponse
{
    [JsonPropertyName("ok")]
    public bool Ok { get; set; }

    [JsonPropertyName("venues")]
    public List<Venue> Venues { get; set; } = new();
}

public sealed class VenueMembershipResponse
{
    [JsonPropertyName("ok")]
    public bool Ok { get; set; }

    [JsonPropertyName("membership")]
    public VenueMembership? Membership { get; set; }
}

public sealed class UpdateVenueRequest
{
    [JsonPropertyName("currency_name")]
    public string? CurrencyName { get; set; }

    [JsonPropertyName("minimal_spend")]
    public int? MinimalSpend { get; set; }

    [JsonPropertyName("background_image")]
    public string? BackgroundImage { get; set; }

    [JsonPropertyName("deck_id")]
    public string? DeckId { get; set; }
}
