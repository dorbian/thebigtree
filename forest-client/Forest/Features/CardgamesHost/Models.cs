using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace Forest.Features.CardgamesHost;

public record CardDeck(
    string deck_id,
    string? name,
    string? theme
);

public record ListDecksResponse(
    bool ok,
    List<CardDeck>? decks,
    string? error
);

public record CardgameSession(
    string session_id,
    string join_code,
    string priestess_token,
    string? player_token,
    string game_id,
    string? deck_id,
    string? background_url,
    string? background_artist_id,
    string? background_artist_name,
    string status,
    int pot,
    int winnings,
    [property: JsonNumberHandling(JsonNumberHandling.AllowReadingFromString)]
    double? created_at
);

public record ListSessionsResponse(
    bool ok,
    List<CardgameSession>? sessions,
    string? error
);

public record CreateSessionResponse(
    bool ok,
    CardgameSession? session,
    string? error
);
