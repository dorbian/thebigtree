using System;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Forest.Features.HuntStaffed
{
    public sealed class HuntAdminApiClient : IDisposable
    {
        private readonly HttpClient _http;
        private readonly string? _apiKey;
        private readonly JsonSerializerOptions _json = new()
        {
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase
        };

        public HuntAdminApiClient(string baseUrl, string? apiKey = null)
        {
            _http = new HttpClient { BaseAddress = new Uri(baseUrl.TrimEnd('/') + "/") };
            _apiKey = string.IsNullOrWhiteSpace(apiKey) ? null : apiKey.Trim();
        }

        private void ApplyAuthHeaders(HttpRequestMessage req)
        {
            if (!string.IsNullOrEmpty(_apiKey))
                req.Headers.Add("X-API-Key", _apiKey);
        }

        public Task<HuntStateResponse> GetStateAsync(string huntId, CancellationToken ct = default)
            => Get<HuntStateResponse>($"hunts/{Uri.EscapeDataString(huntId)}/state", ct);

        public Task<HuntListResponse> ListHuntsAsync(CancellationToken ct = default)
            => Get<HuntListResponse>("hunts", ct);

        public Task<HuntCreateResponse> CreateHuntAsync(string title, int territoryId, string? description, string? rules, bool allowImplicitGroups, CancellationToken ct = default)
            => Post<HuntCreateResponse>("hunts", new
            {
                title = title,
                territory_id = territoryId,
                description = description,
                rules = rules,
                allow_implicit_groups = allowImplicitGroups
            }, ct);

        public Task<HuntJoinResponse> JoinByCodeAsync(string joinCode, string staffName, string? staffId = null, CancellationToken ct = default)
            => Post<HuntJoinResponse>("hunts/join", new { join_code = joinCode, staff_name = staffName, staff_id = staffId }, ct);

        public Task<HuntStaffJoinResponse> JoinStaffAsync(string huntId, string staffName, string? staffId = null, CancellationToken ct = default)
            => Post<HuntStaffJoinResponse>($"hunts/{Uri.EscapeDataString(huntId)}/staff/join", new { staff_name = staffName, staff_id = staffId }, ct);

        public Task<HuntSimpleResponse> ClaimCheckpointAsync(string huntId, string staffId, string checkpointId, CancellationToken ct = default)
            => Post<HuntSimpleResponse>($"hunts/{Uri.EscapeDataString(huntId)}/staff/claim-checkpoint", new { staff_id = staffId, checkpoint_id = checkpointId }, ct);

        public Task<HuntCheckinResponse> CheckInAsync(string huntId, string staffId, string groupId, string checkpointId, object? evidence = null, CancellationToken ct = default)
            => Post<HuntCheckinResponse>($"hunts/{Uri.EscapeDataString(huntId)}/checkins", new { staff_id = staffId, group_id = groupId, checkpoint_id = checkpointId, evidence = evidence ?? new { } }, ct);

        public Task<HuntSimpleResponse> StartAsync(string huntId, CancellationToken ct = default)
            => Post<HuntSimpleResponse>($"hunts/{Uri.EscapeDataString(huntId)}/start", new { }, ct);

        public Task<HuntSimpleResponse> EndAsync(string huntId, CancellationToken ct = default)
            => Post<HuntSimpleResponse>($"hunts/{Uri.EscapeDataString(huntId)}/end", new { }, ct);

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
}
