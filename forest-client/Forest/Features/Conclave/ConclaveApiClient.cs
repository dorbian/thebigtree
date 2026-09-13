using System;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Forest.Features.Conclave;

public sealed class ConclaveApiClient : IDisposable
{
    private readonly HttpClient _http;
    private readonly string? _apiKey;
    private readonly JsonSerializerOptions _json = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        PropertyNameCaseInsensitive = true
    };

    public ConclaveApiClient(string baseUrl, string? apiKey = null)
    {
        _http = new HttpClient
        {
            BaseAddress = new Uri(baseUrl.TrimEnd('/') + "/"),
            Timeout = TimeSpan.FromSeconds(10)
        };
        _apiKey = string.IsNullOrWhiteSpace(apiKey) ? null : apiKey.Trim();
    }

    private void ApplyAuthHeaders(HttpRequestMessage req)
    {
        if (!string.IsNullOrEmpty(_apiKey))
            req.Headers.Add("X-API-Key", _apiKey);
    }

    public Task<ConclaveSessionsResponse> ListAsync(bool includeEnded = false, CancellationToken ct = default)
        => Get<ConclaveSessionsResponse>($"admin/conclave/sessions?include_ended={(includeEnded ? "1" : "0")}", ct);

    public Task<ConclaveSessionResponse> GetAsync(string gameId, CancellationToken ct = default)
        => Get<ConclaveSessionResponse>($"admin/conclave/{Uri.EscapeDataString(gameId)}", ct);

    public Task<ConclaveSessionResponse> StartAsync(string gameId, CancellationToken ct = default)
        => Post<ConclaveSessionResponse>($"admin/conclave/{Uri.EscapeDataString(gameId)}/start", ct);

    public Task<ConclaveSessionResponse> AdvanceAsync(string gameId, CancellationToken ct = default)
        => Post<ConclaveSessionResponse>($"admin/conclave/{Uri.EscapeDataString(gameId)}/advance", ct);

    public Task<ConclaveSessionResponse> EndAsync(string gameId, CancellationToken ct = default)
        => Post<ConclaveSessionResponse>($"admin/conclave/{Uri.EscapeDataString(gameId)}/end", ct);

    private async Task<T> Get<T>(string path, CancellationToken ct)
    {
        using var req = new HttpRequestMessage(HttpMethod.Get, path);
        ApplyAuthHeaders(req);
        using var resp = await _http.SendAsync(req, ct).ConfigureAwait(false);
        var payload = await resp.Content.ReadAsStringAsync(ct).ConfigureAwait(false);
        resp.EnsureSuccessStatusCode();
        return JsonSerializer.Deserialize<T>(payload, _json)!;
    }

    private async Task<T> Post<T>(string path, CancellationToken ct)
    {
        using var req = new HttpRequestMessage(HttpMethod.Post, path)
        {
            Content = new StringContent("{}", Encoding.UTF8, "application/json")
        };
        ApplyAuthHeaders(req);
        using var resp = await _http.SendAsync(req, ct).ConfigureAwait(false);
        var payload = await resp.Content.ReadAsStringAsync(ct).ConfigureAwait(false);
        if (!resp.IsSuccessStatusCode)
        {
            // Preserve structured game errors for the host panel when possible.
            try
            {
                var structured = JsonSerializer.Deserialize<T>(payload, _json);
                if (structured is not null)
                    return structured;
            }
            catch { }
            resp.EnsureSuccessStatusCode();
        }
        return JsonSerializer.Deserialize<T>(payload, _json)!;
    }

    public void Dispose() => _http.Dispose();
}
