using System.Collections.Generic;

namespace Forest.Features.HuntStaffed
{
    public sealed class HuntInfo
    {
        public string? hunt_id { get; set; }
        public string? title { get; set; }
        public string? description { get; set; }
        public string? rules { get; set; }
        public int territory_id { get; set; }
        public string? join_code { get; set; }
        public double created_at { get; set; }
        public bool started { get; set; }
        public bool ended { get; set; }
        public bool active { get; set; }
        public bool allow_implicit_groups { get; set; }
    }

    public sealed class HuntPos
    {
        public float x { get; set; }
        public float y { get; set; }
        public float z { get; set; }
    }

    public sealed class HuntCheckpoint
    {
        public string? checkpoint_id { get; set; }
        public string? label { get; set; }
        public int territory_id { get; set; }
        public HuntPos? pos { get; set; }
        public float radius_m { get; set; }
        public List<string>? claimed_by { get; set; }
        public double created_at { get; set; }
    }

    public sealed class HuntGroup
    {
        public string? group_id { get; set; }
        public string? name { get; set; }
        public string? captain_name { get; set; }
        public int score { get; set; }
        public List<string>? visited_checkpoints { get; set; }
        public double created_at { get; set; }
    }

    public sealed class HuntStaff
    {
        public string? staff_id { get; set; }
        public string? name { get; set; }
        public string? checkpoint_id { get; set; }
        public double joined_at { get; set; }
    }

    public sealed class HuntCheckin
    {
        public string? checkin_id { get; set; }
        public string? group_id { get; set; }
        public string? checkpoint_id { get; set; }
        public string? staff_id { get; set; }
        public double ts { get; set; }
        public Dictionary<string, object>? evidence { get; set; }
    }

    public sealed class HuntStateResponse
    {
        public bool ok { get; set; }
        public string? error { get; set; }
        public HuntInfo? hunt { get; set; }
        public List<HuntCheckpoint>? checkpoints { get; set; }
        public List<HuntGroup>? groups { get; set; }
        public List<HuntStaff>? staff { get; set; }
        public List<HuntCheckin>? checkins { get; set; }
    }

    public sealed class HuntJoinResponse
    {
        public bool ok { get; set; }
        public string? error { get; set; }
        public string? hunt_id { get; set; }
        public string? staff_id { get; set; }
        public HuntStateResponse? state { get; set; }
    }

    public sealed class HuntSimpleResponse
    {
        public bool ok { get; set; }
        public string? error { get; set; }
        public string? message { get; set; }
    }

    public sealed class HuntListResponse
    {
        public bool ok { get; set; }
        public string? error { get; set; }
        public List<HuntInfo>? hunts { get; set; }
    }

    public sealed class HuntCreateResponse
    {
        public bool ok { get; set; }
        public string? error { get; set; }
        public HuntInfo? hunt { get; set; }
    }

    public sealed class HuntStaffJoinResponse
    {
        public bool ok { get; set; }
        public string? error { get; set; }
        public HuntStaff? staff { get; set; }
    }

    public sealed class HuntCheckinResponse
    {
        public bool ok { get; set; }
        public string? error { get; set; }
        public HuntCheckin? checkin { get; set; }
    }
}
