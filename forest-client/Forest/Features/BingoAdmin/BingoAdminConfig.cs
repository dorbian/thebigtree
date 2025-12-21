using Dalamud.Configuration;
using Dalamud.Plugin;
using System;

namespace Forest.Features.BingoAdmin
{
    [Serializable]
    public class BingoAdminConfig : IPluginConfiguration
    {
        public int Version { get; set; } = 1;

        public string BaseUrl { get; set; } = "https://server.thebigtree.life:8443";
        public string? ApiKey { get; set; } = null;

        public string? LastSelectedGameId { get; set; }

        [NonSerialized] private IDalamudPluginInterface? _pi;

        public void Initialize(IDalamudPluginInterface pi) => _pi = pi;
        public void Save() => _pi?.SavePluginConfig(this);
    }
}
