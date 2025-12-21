namespace Forest.Features.BingoAdmin;

public record GameStateEnvelope(
    bool active,
    GameInfo game,
    GameStats stats
);

public record GameInfo(
    string game_id,
    string title,
    string header,
    string header_text,
    int price,
    string currency,
    int max_cards_per_player,
    int pot,
    int[] called,
    int? last_called,
    bool started,
    string stage,
    Payouts payouts,
    string? background,
    string? theme_color,
    bool active,
    Claim[]? claims
);

public record GameStats(
    int cards,
    int players
);

public record Payouts(
    int single,
    int @double,
    int full
);

public record Claim(
    long? ts,
    string? owner_name,
    string? card_id,
    string? stage,
    bool pending,
    bool denied,
    string? source
);

public record OwnerSummary(
    string owner_name,
    int cards,
    long last_purchase,
    string? token
);

public record OwnersResponse(
    bool ok,
    OwnerSummary[] owners
);

public record OwnerCardsResponse(
    bool ok,
    GameInfo game,
    string owner,
    CardInfo[] cards
);

public record CardInfo(
    string card_id,
    int[][] numbers,
    bool[][] marks
);

public record ListGamesResponse(
    bool ok,
    List<BingoGame>? games
);

public record BingoGame(
    string game_id,
    string title,
    long created_at,
    bool active,
    string stage,
    int pot
);

public record BuyResponse(
    bool ok,
    CardInfo[]? cards,
    string? error
);

public record RollResponse(
    bool ok,
    int[]? called,
    string? error
);

public record SimpleResponse(
    bool ok,
    string? message,
    string? error
);

public record DeleteResponse(
    bool ok,
    string? deleted,
    string? error
);
