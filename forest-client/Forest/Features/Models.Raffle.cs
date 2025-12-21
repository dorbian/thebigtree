// File: Models.Raffle.cs
using System;
using System.Collections.Generic;

namespace Forest
{
    [Serializable]
    public class RaffleEntry
    {
        public string Name { get; set; } = "";
        public DateTime JoinedAtUtc { get; set; } = DateTime.UtcNow;
        public int TicketNumber { get; set; } = 0;
        public string Source { get; set; } = "";
    }

    [Serializable]
    public class RaffleWinner
    {
        public string Name { get; set; } = "";
        public int TicketNumber { get; set; } = 0;
    }

    [Serializable]
    public class RaffleState
    {
        public string Title { get; set; } = "Forest Raffle";
        public string Description { get; set; } = "";
        public string JoinPhrase { get; set; } = "!join";
        public int SignupMinutes { get; set; } = 5;
        public int WinnersCount { get; set; } = 1;
        public bool AllowSay { get; set; } = true;
        public bool AllowShout { get; set; } = true;
        public bool AllowYell { get; set; } = false;
        public bool AllowParty { get; set; } = true;
        public bool AllowTell { get; set; } = false;
        public bool AllowAlts { get; set; } = false;
        public bool AllowRepeatWinners { get; set; } = false;
        public bool AutoDrawOnClose { get; set; } = true;
        public bool IsOpen { get; set; } = false;
        public DateTime? StartedAtUtc { get; set; } = null;
        public DateTime? EndsAtUtc { get; set; } = null;
        public string HostSalt { get; set; } = "";
        public string? SeedSource { get; set; } = null;
        public string? SeedHash { get; set; } = null;
        public string? RandomBytes { get; set; } = null;
        public string? WebhookUrl { get; set; } = null;

        public List<RaffleEntry> Entries { get; set; } = new();
        public List<RaffleWinner> Winners { get; set; } = new();
    }
}
