// File: Models.MurderMystery.cs
using System;
using System.Collections.Generic;
using System.Linq;

namespace Forest
{
    // Data model for a player
    [Serializable]
    public class PlayerData
    {
        public string Name { get; set; } = "";
        public string Notes { get; set; } = "";

        // Dynamic whispers keyed by round index
        public Dictionary<int, string> Whispers { get; set; } = new();

        // Legacy fields (kept for migration; safe to keep or remove later)
        [Obsolete("Use Whispers dictionary instead")] public string? Whisper1 { get; set; }
        [Obsolete("Use Whispers dictionary instead")] public string? Whisper2 { get; set; }
        [Obsolete("Use Whispers dictionary instead")] public string? Whisper3 { get; set; }
        [Obsolete("Use Whispers dictionary instead")] public Dictionary<int, string>? ExtraWhispers { get; set; }

        public string GetWhisper(int index) =>
            Whispers.TryGetValue(index, out var value) ? value : "";

        public void SetWhisper(int index, string value)
        {
            if (string.IsNullOrEmpty(value)) Whispers.Remove(index);
            else Whispers[index] = value;
        }

        public int GetWhisperCount() =>
            Whispers.Keys.Count > 0 ? Whispers.Keys.Max() + 1 : 0;
    }

    // Data model for Murder Mystery
    [Serializable]
    public class MurderMysteryData
    {
        public string Title { get; set; } = "";
        public string Description { get; set; } = "";
        public List<string> ActivePlayers { get; set; } = new();
        public List<string> DeadPlayers { get; set; } = new();
        public List<string> ImprisonedPlayers { get; set; } = new();
        public string Killer { get; set; } = "";
        public string Prize { get; set; } = "";

        // Dynamic timers/hints
        public Dictionary<int, string> HintTimes { get; set; } = new();
        public Dictionary<int, string> HintTexts { get; set; } = new();
        public Dictionary<int, DateTime> TimerEndTimes { get; set; } = new();
        public Dictionary<int, bool> TimerNotified { get; set; } = new();

        // Legacy example
        public bool? Timer3Notified { get; set; }

        public string GetHintTime(int index) =>
            HintTimes.TryGetValue(index, out var value) ? value : "";
        public void SetHintTime(int index, string value)
        {
            if (string.IsNullOrEmpty(value)) HintTimes.Remove(index);
            else HintTimes[index] = value;
        }

        public string GetHintText(int index) =>
            HintTexts.TryGetValue(index, out var value) ? value : "";
        public void SetHintText(int index, string value)
        {
            if (string.IsNullOrEmpty(value)) HintTexts.Remove(index);
            else HintTexts[index] = value;
        }

        public DateTime GetTimerEndTime(int index) =>
            TimerEndTimes.TryGetValue(index, out var value) ? value : DateTime.MinValue;
        public void SetTimerEndTime(int index, DateTime value)
        {
            if (value == DateTime.MinValue) TimerEndTimes.Remove(index);
            else TimerEndTimes[index] = value;
        }

        public bool GetTimerNotified(int index) =>
            TimerNotified.TryGetValue(index, out var value) && value;
        public void SetTimerNotified(int index, bool value)
        {
            if (!value) TimerNotified.Remove(index);
            else TimerNotified[index] = value;
        }
    }
}
