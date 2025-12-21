// File: Models.GlamRoulette.cs
using System;
using System.Collections.Generic;

namespace Forest
{
    [Serializable]
    public class GlamTheme
    {
        public string Text { get; set; } = "";
    }

    [Serializable]
    public class GlamContestant
    {
        public string Name { get; set; } = "";
        public int Order { get; set; } = 0;
    }

    [Serializable]
    public class GlamRouletteState
    {
        public string Title { get; set; } = "Glam Roulette";
        public string VoteKeyword { get; set; } = "!vote";
        public int RoundMinutes { get; set; } = 3;
        public bool AllowSay { get; set; } = true;
        public bool AllowShout { get; set; } = true;
        public bool AllowYell { get; set; } = false;
        public bool AllowParty { get; set; } = true;
        public bool AllowTell { get; set; } = false;
        public bool VotingOpen { get; set; } = false;
        public bool RoundActive { get; set; } = false;
        public DateTime? StartedAtUtc { get; set; } = null;
        public DateTime? EndsAtUtc { get; set; } = null;
        public string CurrentTheme { get; set; } = "";
        public List<GlamTheme> Themes { get; set; } = new();
        public List<GlamContestant> Contestants { get; set; } = new();
        public Dictionary<string, string> VotesByVoter { get; set; } = new();
    }
}
