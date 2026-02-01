using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Forest.Features.Events;

public sealed class EventsApiClient : IDisposable
{
    private readonly HttpClient _http;
    private readonly string? _apiKey;
    private readonly JsonSerializerOptions _json = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase
    };

    public EventsApiClient(string baseUrl, string? apiKey = null)
    {
        _http = new HttpClient { BaseAddress = new Uri(baseUrl.TrimEnd('/') + "/") };
        _apiKey = string.IsNullOrWhiteSpace(apiKey) ? null : apiKey.Trim();
    }

    private void ApplyAuthHeaders(HttpRequestMessage req)
    {
        if (!string.IsNullOrEmpty(_apiKey))
            req.Headers.Add("X-API-Key", _apiKey);
    }

    public async Task<List<EventInfo>> ListEventsAsync(int? venueId = null, bool includeEnded = false, CancellationToken ct = default)
    {
        var query = $"?include_ended={(includeEnded ? "1" : "0")}";
        if (venueId.HasValue)
            query += $"&venue_id={venueId.Value}";
        var req = new HttpRequestMessage(HttpMethod.Get, $"admin/events{query}");
        ApplyAuthHeaders(req);
        var resp = await _http.SendAsync(req, ct).ConfigureAwait(false);
        if (!resp.IsSuccessStatusCode)
            return new List<EventInfo>();
        var payload = await resp.Content.ReadAsStringAsync(ct).ConfigureAwait(false);
        var result = JsonSerializer.Deserialize<ListEventsResponse>(payload, _json);
        return result?.Events ?? new List<EventInfo>();
    }

    public async Task<EventInfo?> GetEventAsync(string code, CancellationToken ct = default)
    {
        var req = new HttpRequestMessage(HttpMethod.Get, $"api/events/{Uri.EscapeDataString(code)}");
        ApplyAuthHeaders(req);
        var resp = await _http.SendAsync(req, ct).ConfigureAwait(false);
        if (!resp.IsSuccessStatusCode)
            return null;
        var payload = await resp.Content.ReadAsStringAsync(ct).ConfigureAwait(false);
        var result = JsonSerializer.Deserialize<EventInfoResponse>(payload, _json);
        return result?.Event;
    }

    public async Task<EventInfo?> CreateEventAsync(CreateEventRequest request, CancellationToken ct = default)
    {
        var json = JsonSerializer.Serialize(request, _json);
        var content = new StringContent(json, Encoding.UTF8, "application/json");
        var req = new HttpRequestMessage(HttpMethod.Post, "admin/events/upsert") { Content = content };
        ApplyAuthHeaders(req);
        var resp = await _http.SendAsync(req, ct).ConfigureAwait(false);
        if (!resp.IsSuccessStatusCode)
            return null;
        var payload = await resp.Content.ReadAsStringAsync(ct).ConfigureAwait(false);
        var result = JsonSerializer.Deserialize<EventInfoResponse>(payload, _json);
        return result?.Event;
    }

    public async Task<bool> EndEventAsync(int eventId, CancellationToken ct = default)
    {
        var body = new { event_id = eventId };
        var json = JsonSerializer.Serialize(body, _json);
        var content = new StringContent(json, Encoding.UTF8, "application/json");
        var req = new HttpRequestMessage(HttpMethod.Post, "admin/events/end") { Content = content };
        ApplyAuthHeaders(req);
        var resp = await _http.SendAsync(req, ct).ConfigureAwait(false);
        return resp.IsSuccessStatusCode;
    }

    public async Task<List<EventPlayer>> GetEventPlayersAsync(int eventId, CancellationToken ct = default)
    {
        var req = new HttpRequestMessage(HttpMethod.Get, $"admin/events/{eventId}/players");
        ApplyAuthHeaders(req);
        var resp = await _http.SendAsync(req, ct).ConfigureAwait(false);
        if (!resp.IsSuccessStatusCode)
            return new List<EventPlayer>();
        var payload = await resp.Content.ReadAsStringAsync(ct).ConfigureAwait(false);
        var result = JsonSerializer.Deserialize<EventPlayersResponse>(payload, _json);
        return result?.Players ?? new List<EventPlayer>();
    }

    public async Task<List<EventGameSession>> GetEventGamesAsync(string code, CancellationToken ct = default)
    {
        var req = new HttpRequestMessage(HttpMethod.Get, $"api/events/{Uri.EscapeDataString(code)}/games");
        ApplyAuthHeaders(req);
        var resp = await _http.SendAsync(req, ct).ConfigureAwait(false);
        if (!resp.IsSuccessStatusCode)
            return new List<EventGameSession>();
        var payload = await resp.Content.ReadAsStringAsync(ct).ConfigureAwait(false);
        var result = JsonSerializer.Deserialize<EventGamesResponse>(payload, _json);
        return result?.Games ?? new List<EventGameSession>();
    }

    public async Task<(bool Ok, string? JoinUrl, string? Error)> CreateEventGameAsync(string code, string gameId, CancellationToken ct = default)
    {
        var body = new { game_id = gameId };
        var json = JsonSerializer.Serialize(body, _json);
        var content = new StringContent(json, Encoding.UTF8, "application/json");
        var req = new HttpRequestMessage(HttpMethod.Post, $"api/events/{Uri.EscapeDataString(code)}/games/create") { Content = content };
        ApplyAuthHeaders(req);
        var resp = await _http.SendAsync(req, ct).ConfigureAwait(false);
        var payload = await resp.Content.ReadAsStringAsync(ct).ConfigureAwait(false);
        var result = JsonSerializer.Deserialize<EventGameCreateResponse>(payload, _json);
        return (result?.Ok ?? false, result?.JoinUrl, result?.Error);
    }

    public async Task<bool> SetPlayerWalletAsync(int eventId, int userId, int balance, CancellationToken ct = default)
    {
        var body = new { user_id = userId, balance };
        var json = JsonSerializer.Serialize(body, _json);
        var content = new StringContent(json, Encoding.UTF8, "application/json");
        var req = new HttpRequestMessage(HttpMethod.Post, $"admin/events/{eventId}/wallets/set") { Content = content };
        ApplyAuthHeaders(req);
        var resp = await _http.SendAsync(req, ct).ConfigureAwait(false);
        return resp.IsSuccessStatusCode;
    }

    public void Dispose()
    {
        _http.Dispose();
    }
}
