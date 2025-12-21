// File: Models.SpinWheel.cs
using System;
using System.Collections.Generic;

namespace Forest
{
    [Serializable]
    public class WheelPrompt
    {
        public string Text { get; set; } = "";
        public int Weight { get; set; } = 1;
        public int LastUsedSpin { get; set; } = -1;
    }

    [Serializable]
    public class SpinWheelState
    {
        public string Title { get; set; } = "Spin the Wheel";
        public string AnnouncementTemplate { get; set; } = "[Wheel] {prompt}";
        public string PunishmentTemplate { get; set; } = "[Wheel][Punishment] {prompt}";
        public int CooldownSpins { get; set; } = 2;
        public bool AnnounceInChat { get; set; } = true;
        public bool UsePunishments { get; set; } = false;
        public bool PunishLoserOnly { get; set; } = true;
        public int SpinCount { get; set; } = 0;
        public string LastPrompt { get; set; } = "";
        public List<WheelPrompt> Prompts { get; set; } = new();
        public List<WheelPrompt> PunishmentPrompts { get; set; } = new();
    }
}
