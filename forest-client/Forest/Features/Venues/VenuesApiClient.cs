using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Forest.Features.Venues;

public sealed class VenuesApiClient : IDisposable
{
    private readonly HttpClient _http;
    private readonly string? _apiKey;
    private readonly JsonSerializerOptions _json = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase
    };

    public VenuesApiClient(string baseUrl, string? apiKey = null)
    {
        _http = new HttpClient { BaseAddress = new Uri(baseUrl.TrimEnd('/') + "/") };
        _apiKey = string.IsNullOrWhiteSpace(apiKey) ? null : apiKey.Trim();
    }

    private void ApplyAuthHeaders(HttpRequestMessage req)
    {
        if (!string.IsNullOrEmpty(_apiKey))
            req.Headers.Add("X-API-Key", _apiKey);
    }

    public async Task<List<Venue>> ListVenuesAsync(CancellationToken ct = default)
    {
        var req = new HttpRequestMessage(HttpMethod.Get, "admin/venues/list");
        ApplyAuthHeaders(req);
        var resp = await _http.SendAsync(req, ct).ConfigureAwait(false);
        var payload = await resp.Content.ReadAsStringAsync(ct).ConfigureAwait(false);
        var result = JsonSerializer.Deserialize<ListVenuesResponse>(payload, _json);
        return result?.Venues ?? new List<Venue>();
    }

    public async Task<VenueMembership?> GetMyVenueAsync(CancellationToken ct = default)
    {
        var req = new HttpRequestMessage(HttpMethod.Get, "admin/venue/me");
        ApplyAuthHeaders(req);
        var resp = await _http.SendAsync(req, ct).ConfigureAwait(false);
        if (!resp.IsSuccessStatusCode)
            return null;
        var payload = await resp.Content.ReadAsStringAsync(ct).ConfigureAwait(false);
        var result = JsonSerializer.Deserialize<VenueMembershipResponse>(payload, _json);
        return result?.Membership;
    }

    public async Task<bool> AssignVenueAsync(int venueId, CancellationToken ct = default)
    {
        var body = new { venue_id = venueId };
        var json = JsonSerializer.Serialize(body, _json);
        var content = new StringContent(json, Encoding.UTF8, "application/json");
        var req = new HttpRequestMessage(HttpMethod.Post, "admin/venue/assign") { Content = content };
        ApplyAuthHeaders(req);
        var resp = await _http.SendAsync(req, ct).ConfigureAwait(false);
        return resp.IsSuccessStatusCode;
    }

    public async Task<bool> UpdateVenueAsync(UpdateVenueRequest request, CancellationToken ct = default)
    {
        var json = JsonSerializer.Serialize(request, _json);
        var content = new StringContent(json, Encoding.UTF8, "application/json");
        var req = new HttpRequestMessage(HttpMethod.Post, "venues/update") { Content = content };
        ApplyAuthHeaders(req);
        var resp = await _http.SendAsync(req, ct).ConfigureAwait(false);
        return resp.IsSuccessStatusCode;
    }

    public void Dispose()
    {
        _http.Dispose();
    }
}
