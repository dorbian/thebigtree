using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Forest.Features.BingoAdmin
{
    public sealed class BingoAdminApiClient : IDisposable
    {
        private readonly HttpClient _http;
        private readonly string? _apiKey;
        private readonly JsonSerializerOptions _json = new()
        {
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase
        };

        public BingoAdminApiClient(string baseUrl, string? apiKey = null)
        {
            _http = new HttpClient { BaseAddress = new Uri(baseUrl.TrimEnd('/') + "/") };
            _apiKey = string.IsNullOrWhiteSpace(apiKey) ? null : apiKey.Trim();
        }

        private void ApplyAuthHeaders(HttpRequestMessage req)
        {
            if (!string.IsNullOrEmpty(_apiKey))
                req.Headers.Add("X-API-Key", _apiKey);
        }

        public async Task<List<BingoGame>> ListGamesAsync(CancellationToken ct = default)
        {
            var resp = await Get<ListGamesResponse>("bingo/games", ct).ConfigureAwait(false);
            return resp?.games ?? new List<BingoGame>();
        }

        public Task<GameStateEnvelope> GetStateAsync(string gameId, CancellationToken ct = default)
            => Get<GameStateEnvelope>($"bingo/{Uri.EscapeDataString(gameId)}", ct);

        public Task<OwnersResponse> GetOwnersAsync(string gameId, CancellationToken ct = default)
            => Get<OwnersResponse>($"bingo/{Uri.EscapeDataString(gameId)}/owners", ct);

        public Task<OwnerCardsResponse> GetOwnerCardsAsync(string gameId, string owner, CancellationToken ct = default)
            => Get<OwnerCardsResponse>($"bingo/{Uri.EscapeDataString(gameId)}/owner/{Uri.EscapeDataString(owner)}/cards", ct);

        public Task<RollResponse> RollAsync(string gameId, CancellationToken ct = default)
            => Post<RollResponse>("bingo/roll", new { game_id = gameId }, ct);

        public Task<RollResponse> CallNumberAsync(string gameId, int number, CancellationToken ct = default)
            => Post<RollResponse>("bingo/call", new { game_id = gameId, number = number }, ct);

        public Task<SimpleResponse> StartGameAsync(string gameId, CancellationToken ct = default)
            => Post<SimpleResponse>("bingo/start", new { game_id = gameId }, ct);

        public Task<SimpleResponse> AdvanceStageAsync(string gameId, CancellationToken ct = default)
            => Post<SimpleResponse>("bingo/advance-stage", new { game_id = gameId }, ct);

        public Task<SimpleResponse> EndGameAsync(string gameId, CancellationToken ct = default)
            => Post<SimpleResponse>("bingo/end", new { game_id = gameId }, ct);

        public Task<SimpleResponse> ApproveClaimAsync(string gameId, string cardId, CancellationToken ct = default)
            => Post<SimpleResponse>("bingo/claim-approve", new { game_id = gameId, card_id = cardId }, ct);

        public Task<SimpleResponse> DenyClaimAsync(string gameId, string cardId, CancellationToken ct = default)
            => Post<SimpleResponse>("bingo/claim-deny", new { game_id = gameId, card_id = cardId }, ct);

        public async Task<BuyResponse> BuyAsync(string gameId, string ownerName, int count = 1, CancellationToken ct = default)
        {
            var body = new { game_id = gameId, owner_name = ownerName, quantity = count };
            var content = new StringContent(JsonSerializer.Serialize(body, _json), Encoding.UTF8, "application/json");
            using var req = new HttpRequestMessage(HttpMethod.Post, "bingo/buy") { Content = content };
            ApplyAuthHeaders(req);
            using var resp = await _http.SendAsync(req, ct).ConfigureAwait(false);
            var payload = await resp.Content.ReadAsStringAsync(ct).ConfigureAwait(false);
            if (!resp.IsSuccessStatusCode)
            {
                try
                {
                    var err = JsonSerializer.Deserialize<BuyResponse>(payload, _json);
                    if (!string.IsNullOrWhiteSpace(err?.error))
                        throw new InvalidOperationException(err.error);
                }
                catch (Exception)
                {
                    throw new InvalidOperationException($"Buy failed: {resp.StatusCode} {payload}");
                }
            }
            return JsonSerializer.Deserialize<BuyResponse>(payload, _json)!;
        }

        public Task<DeleteResponse> DeleteGameAsync(string gameId, CancellationToken ct = default)
            => Delete<DeleteResponse>($"bingo/{Uri.EscapeDataString(gameId)}", ct);

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

        private async Task<T> Delete<T>(string path, CancellationToken ct)
        {
            using var req = new HttpRequestMessage(HttpMethod.Delete, path);
            ApplyAuthHeaders(req);
            using var resp = await _http.SendAsync(req, ct).ConfigureAwait(false);
            var payload = await resp.Content.ReadAsStringAsync(ct).ConfigureAwait(false);
            resp.EnsureSuccessStatusCode();
            return JsonSerializer.Deserialize<T>(payload, _json)!;
        }

        public void Dispose() => _http.Dispose();
    }
}
