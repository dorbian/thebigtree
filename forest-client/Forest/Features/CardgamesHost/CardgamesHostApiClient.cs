using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Forest.Features.CardgamesHost;

public sealed class CardgamesHostApiClient : IDisposable
{
    private readonly HttpClient _http;
    private readonly string? _apiKey;
    private readonly JsonSerializerOptions _json = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase
    };

    public CardgamesHostApiClient(string baseUrl, string? apiKey = null)
    {
        _http = new HttpClient { BaseAddress = new Uri(baseUrl.TrimEnd('/') + "/") };
        _apiKey = string.IsNullOrWhiteSpace(apiKey) ? null : apiKey.Trim();
    }

    private void ApplyAuthHeaders(HttpRequestMessage req)
    {
        if (!string.IsNullOrEmpty(_apiKey))
            req.Headers.Add("X-API-Key", _apiKey);
    }

    public async Task<List<CardDeck>> ListDecksAsync(CancellationToken ct = default)
    {
        var resp = await Get<ListDecksResponse>("api/tarot/decks", ct).ConfigureAwait(false);
        return resp?.decks ?? new List<CardDeck>();
    }

    public async Task<List<CardgameSession>> ListSessionsAsync(string gameId, CancellationToken ct = default)
    {
        var resp = await Get<ListSessionsResponse>($"api/cardgames/{Uri.EscapeDataString(gameId)}/sessions", ct).ConfigureAwait(false);
        return resp?.sessions ?? new List<CardgameSession>();
    }

    public Task<CreateSessionResponse> CreateSessionAsync(
        string gameId,
        int pot,
        string? deckId,
        string? currency,
        CancellationToken ct = default)
    {
        var body = new Dictionary<string, object?>
        {
            ["pot"] = pot,
            ["deck_id"] = string.IsNullOrWhiteSpace(deckId) ? null : deckId,
            ["currency"] = string.IsNullOrWhiteSpace(currency) ? null : currency
        };
        return Post<CreateSessionResponse>($"api/cardgames/{Uri.EscapeDataString(gameId)}/sessions", body, ct);
    }

    public Task<JoinSessionResponse> JoinSessionAsync(string gameId, string joinCode, CancellationToken ct = default)
    {
        return Post<JoinSessionResponse>(
            $"api/cardgames/{Uri.EscapeDataString(gameId)}/sessions/{Uri.EscapeDataString(joinCode)}/join",
            new { },
            ct
        );
    }

    public Task<CardgameStateResponse> GetStateAsync(string gameId, string joinCode, CancellationToken ct = default)
    {
        return Get<CardgameStateResponse>(
            $"api/cardgames/{Uri.EscapeDataString(gameId)}/sessions/{Uri.EscapeDataString(joinCode)}/state?view=priestess",
            ct
        );
    }

    public Task<CardgameActionResponse> StartSessionAsync(string gameId, string sessionId, string priestessToken, CancellationToken ct = default)
    {
        var body = new Dictionary<string, object?> { ["token"] = priestessToken };
        return Post<CardgameActionResponse>(
            $"api/cardgames/{Uri.EscapeDataString(gameId)}/sessions/{Uri.EscapeDataString(sessionId)}/start",
            body,
            ct
        );
    }

    public Task<CardgameActionResponse> FinishSessionAsync(string gameId, string sessionId, string priestessToken, CancellationToken ct = default)
    {
        var body = new Dictionary<string, object?> { ["token"] = priestessToken };
        return Post<CardgameActionResponse>(
            $"api/cardgames/{Uri.EscapeDataString(gameId)}/sessions/{Uri.EscapeDataString(sessionId)}/finish",
            body,
            ct
        );
    }

    public Task<CardgameActionResponse> HostActionAsync(
        string gameId,
        string sessionId,
        string priestessToken,
        string action,
        CancellationToken ct = default)
    {
        var body = new Dictionary<string, object?>
        {
            ["token"] = priestessToken,
            ["action"] = action
        };
        return Post<CardgameActionResponse>(
            $"api/cardgames/{Uri.EscapeDataString(gameId)}/sessions/{Uri.EscapeDataString(sessionId)}/host-action",
            body,
            ct
        );
    }

    public Task<CardgameActionResponse> PlayerActionAsync(
        string gameId,
        string sessionId,
        string playerToken,
        string action,
        CancellationToken ct = default)
    {
        var body = new Dictionary<string, object?>
        {
            ["token"] = playerToken,
            ["action"] = action
        };
        return Post<CardgameActionResponse>(
            $"api/cardgames/{Uri.EscapeDataString(gameId)}/sessions/{Uri.EscapeDataString(sessionId)}/action",
            body,
            ct
        );
    }

    private async Task<T> Get<T>(string path, CancellationToken ct)
    {
        using var req = new HttpRequestMessage(HttpMethod.Get, path);
        ApplyAuthHeaders(req);
        using var resp = await _http.SendAsync(req, ct).ConfigureAwait(false);
        var payload = await resp.Content.ReadAsStringAsync(ct).ConfigureAwait(false);
        resp.EnsureSuccessStatusCode();
        return JsonSerializer.Deserialize<T>(payload, _json)!;
    }

    private async Task<T> Post<T>(string path, object body, CancellationToken ct)
    {
        var content = new StringContent(JsonSerializer.Serialize(body, _json), Encoding.UTF8, "application/json");
        using var req = new HttpRequestMessage(HttpMethod.Post, path) { Content = content };
        ApplyAuthHeaders(req);
        using var resp = await _http.SendAsync(req, ct).ConfigureAwait(false);
        var payload = await resp.Content.ReadAsStringAsync(ct).ConfigureAwait(false);
        resp.EnsureSuccessStatusCode();
        return JsonSerializer.Deserialize<T>(payload, _json)!;
    }

    public void Dispose() => _http.Dispose();
}
