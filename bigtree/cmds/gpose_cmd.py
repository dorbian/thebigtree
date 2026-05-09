"""
G-Pose Contest Slash Commands for BigTree.
A Discord cog that registers all /gpose-* slash commands.
"""

import time as _time
import discord
from discord import app_commands
from discord.ext import commands

import bigtree
from bigtree.modules.permissions import is_bigtree_operator

bot = getattr(bigtree, "bot", None)
GUILD = discord.Object(id=getattr(bigtree, "guildid", 0))


def _status_embed():
    from bigtree.modules.gpose_contest import get_current_week, get_submissions, get_config

    week = get_current_week()
    submissions = get_submissions()
    cfg = get_config()

    embed = discord.Embed(color=0x9B59B6)
    if week is None:
        embed.title = "📸 G-Pose Contest"
        embed.description = "No contest is currently running."
        embed.add_field(name="How to participate", value="Wait for the next contest announcement!", inline=False)
        return embed

    days_left = max(0, round((week.end_ts - _time.time()) / 86400, 1))
    status_icon = {"open": "🟢", "voting": "🟡", "closed": "⚪"}.get(week.status, "⚪")
    sub_chan = cfg.get("submissions_channel_id") or "the submissions channel"

    embed.title = f"{status_icon} G-Pose Contest — Week {week.week}"
    embed.description = f"**Theme:** {week.theme}"
    embed.add_field(name="Status", value=week.status.capitalize(), inline=True)
    embed.add_field(name="Days remaining", value=str(days_left), inline=True)
    embed.add_field(name="Submissions", value=str(len(submissions)), inline=True)
    embed.add_field(
        name="How to enter",
        value=(
            f"Post your G-Pose screenshot in <#{sub_chan}>\n"
            "Then use `/gpose-submit [message_id]` to register."
        ),
        inline=False,
    )
    return embed


class GposeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- Public commands ---

    @app_commands.command(name="gpose-status", description="Show current G-Pose contest status", guild=GUILD)
    async def status(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=_status_embed(), ephemeral=True)

    @app_commands.command(name="gpose-submit", description="Register your G-Pose submission for the current contest",
                         guild=GUILD)
    @app_commands.describe(message_id="The Discord message ID of your G-Pose post")
    async def submit(self, interaction: discord.Interaction, message_id: str):
        from bigtree.modules.gpose_contest import submit_entry, get_current_week

        week = get_current_week()
        if week is None or week.status != "open":
            await interaction.response.send_message(
                "No contest is currently open for submissions.", ephemeral=True,
            )
            return

        result = submit_entry(str(message_id), interaction.user.id, interaction.user.display_name)
        if not result.get("ok"):
            await interaction.response.send_message(f"❌ {result.get('error', 'Unknown error')}", ephemeral=True)
            return

        embed = discord.Embed(
            title="✅ Submission received!",
            description=f"Your G-Pose entry for **Week {week.week}** has been recorded.\nTheme: *{week.theme}*",
            color=0x2ECC71,
        )
        embed.add_field(name="Entry #", value=str(result.get("entry_count")), inline=True)
        embed.set_footer(text="Good luck! 🍀")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="gpose-view", description="See current contest submissions", guild=GUILD)
    async def view(self, interaction: discord.Interaction):
        from bigtree.modules.gpose_contest import get_submissions, get_current_week

        week = get_current_week()
        submissions = get_submissions()

        if week is None:
            await interaction.response.send_message("No contest is running.", ephemeral=True)
            return
        if not submissions:
            await interaction.response.send_message(
                f"No submissions yet for Week {week.week} — *{week.theme}*", ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"📸 G-Pose Submissions — Week {week.week}",
            description=f"Theme: *{week.theme}*",
            color=0xFFD700,
        )
        guild_id = interaction.guild_id or 0
        for sub in submissions[:10]:
            embed.add_field(
                name=sub["user_name"],
                value=f"[Jump](https://discord.com/channels/{guild_id}/{sub.get('channel_id', 0)}/{sub['message_id']})",
                inline=True,
            )
        if len(submissions) > 10:
            embed.set_footer(text=f"And {len(submissions) - 10} more submissions...")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="gpose-leaderboard", description="Show weekly, monthly, and yearly G-Pose champions",
                         guild=GUILD)
    @app_commands.describe(limit="Number of weekly entries to show (default: 20)")
    async def leaderboard(self, interaction: discord.Interaction, limit: int = 20):
        from bigtree.modules.gpose_contest import get_leaderboard

        data = get_leaderboard(limit=limit)
        embed = discord.Embed(title="🏆 G-Pose Leaderboard", color=0xFFD700)

        yearly = data.get("yearly_winners", [])
        if yearly:
            lines = [f"**{y['year']}:** <@{y['user_id']}> ({y.get('wins', 0)} wins)" for y in yearly[-3:]]
            embed.add_field(name="Yearly Champions", value="\n".join(lines) or "—", inline=False)

        monthly = data.get("monthly_winners", [])
        if monthly:
            lines = [f"<@{m['user_id']}> — {m['year']}-{m['month']:02d}" for m in monthly[-6:]]
            embed.add_field(name="Monthly Winners", value="\n".join(lines) or "—", inline=False)

        weekly = data.get("weekly_winners", [])
        if weekly:
            recent = weekly[-10:]
            lines = [f"Wk {w.get('week')} {w.get('year')}/{w.get('month'):02d}: <@{w.get('user_id')}>" for w in reversed(recent)]
            embed.add_field(name="Recent Weekly Winners", value="\n".join(lines) or "—", inline=False)

        if not yearly and not monthly and not weekly:
            embed.add_field(name="No winners yet", value="Be the first! 🏃", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # --- Operator commands ---

    @app_commands.command(name="gpose-start", description="Start a new G-Pose contest week", guild=GUILD)
    @is_bigtree_operator()
    @app_commands.describe(
        theme="The contest theme (e.g. 'Open', 'Duo', 'Mood')",
        duration_days="How many days the contest runs (default: 7)",
    )
    async def start(self, interaction: discord.Interaction, theme: str = "Open", duration_days: float = 7.0):
        from bigtree.modules.gpose_contest import start_contest, get_current_week

        if get_current_week() is not None:
            await interaction.response.send_message(
                "A contest is already in progress. End it first with `/gpose-end`.", ephemeral=True,
            )
            return

        result = start_contest(theme=theme, duration_days=duration_days)
        if not result.get("ok"):
            await interaction.response.send_message(f"❌ {result.get('error')}", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"🏁 G-Pose Contest Week {result['week'].get('week')} Started!",
            description=f"**Theme:** {theme}\n**Duration:** {duration_days} days",
            color=0x9B59B6,
        )
        embed.add_field(name="Days remaining", value=str(result.get("days_remaining")), inline=True)
        embed.add_field(
            name="Next steps",
            value=(
                "1. Announce in the submissions channel\n"
                "2. Let participants submit with `/gpose-submit [message_id]`\n"
                "3. End with `/gpose-end` when voting begins"
            ),
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="gpose-end", description="End the current contest (moves to voting or declares winner)",
                         guild=GUILD)
    @is_bigtree_operator()
    @app_commands.describe(
        winner_user_id="Discord user ID of the winner (omit to move to voting first)",
        winner_message_id="Message ID of the winning post",
    )
    async def end(self, interaction: discord.Interaction, winner_user_id: str = "", winner_message_id: str = ""):
        from bigtree.modules.gpose_contest import end_contest

        wid = int(winner_user_id) if winner_user_id else None
        wmid = str(winner_message_id) if winner_message_id else None

        result = end_contest(winner_user_id=wid, winner_message_id=wmid)
        if not result.get("ok"):
            await interaction.response.send_message(f"❌ {result.get('error')}", ephemeral=True)
            return

        if wid:
            embed = discord.Embed(
                title="🏆 Contest Closed — Winner Declared!",
                description=f"Congratulations <@{wid}>!",
                color=0xFFD700,
            )
            embed.add_field(name="Total entries", value=str(result.get("entries_closed")), inline=True)
        else:
            embed = discord.Embed(
                title="🟡 Contest Moved to Voting",
                description="Use `/gpose-winner` to declare the winner once voting is done.",
                color=0xF39C12,
            )
            embed.add_field(name="Total entries", value=str(result.get("entries_closed")), inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="gpose-winner", description="Set winner for a contest in voting state", guild=GUILD)
    @is_bigtree_operator()
    @app_commands.describe(
        user_id="Discord user ID of the winner",
        message_id="Message ID of the winning post",
    )
    async def winner(self, interaction: discord.Interaction, user_id: str, message_id: str):
        from bigtree.modules.gpose_contest import set_winner

        result = set_winner(int(user_id), str(message_id))
        if not result.get("ok"):
            await interaction.response.send_message(f"❌ {result.get('error')}", ephemeral=True)
            return

        record = result.get("winner", {})
        embed = discord.Embed(
            title="🏆 Winner Set!",
            description=f"<@{user_id}> is the weekly G-Pose champion!",
            color=0xFFD700,
        )
        embed.add_field(name="Theme", value=str(record.get("theme", "unknown")), inline=True)
        embed.add_field(name="Week", value=str(record.get("week")), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="gpose-announce", description="Send a G-Pose contest announcement", guild=GUILD)
    @is_bigtree_operator()
    @app_commands.describe(
        content="The announcement text to send",
        channel_id="Channel ID to post in (optional — uses configured announcements channel)",
    )
    async def announce(self, interaction: discord.Interaction, content: str, channel_id: str = ""):
        from bigtree.modules.gpose_contest import get_config

        cfg = get_config()
        cid = int(channel_id) if channel_id else cfg.get("announcements_channel_id")

        if not cid:
            await interaction.response.send_message(
                "No channel ID configured. Set announcements_channel_id first.", ephemeral=True,
            )
            return

        chan = self.bot.get_channel(cid)
        if not chan:
            await interaction.response.send_message(f"Cannot find channel <#{cid}>.", ephemeral=True)
            return

        try:
            msg = await chan.send(content)
            await interaction.response.send_message(
                f"✅ Announcement sent to <#{cid}>: "
                f"[jump](https://discord.com/channels/{interaction.guild_id}/{cid}/{msg.id})",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.response.send_message(f"Failed to send: {e}", ephemeral=True)

    @app_commands.command(name="gpose-config", description="View G-Pose contest configuration", guild=GUILD)
    @is_bigtree_operator()
    async def config_cmd(self, interaction: discord.Interaction):
        from bigtree.modules.gpose_contest import get_config

        cfg = get_config()

        def show(v):
            return str(v) if v is not None else "Not configured"

        embed = discord.Embed(title="⚙️ G-Pose Contest Configuration", color=0x2ECC71)
        embed.add_field(name="Weekly Winner Role ID", value=show(cfg.get("weekly_role_id")), inline=True)
        embed.add_field(name="Monthly Winner Role ID", value=show(cfg.get("monthly_role_id")), inline=True)
        embed.add_field(name="Yearly Winner Role ID", value=show(cfg.get("yearly_role_id")), inline=True)
        embed.add_field(name="Submitter Role ID", value=show(cfg.get("submitter_role_id")), inline=True)
        embed.add_field(name="Submissions Channel", value=show(cfg.get("submissions_channel_id")), inline=True)
        embed.add_field(name="Announcements Channel", value=show(cfg.get("announcements_channel_id")), inline=True)
        embed.add_field(name="Poser's Hall Channel", value=show(cfg.get("posers_hall_channel_id")), inline=True)
        embed.add_field(name="Voting Emoji", value=show(cfg.get("voting_emoji")), inline=True)
        embed.add_field(name="Contest Open", value=str(cfg.get("submission_open", False)), inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="gpose-monthly", description="Check if a month is ready for the monthly vote",
                         guild=GUILD)
    @is_bigtree_operator()
    @app_commands.describe(
        year="Year (default: current year)",
        month="Month (default: current month)",
    )
    async def monthly_check(self, interaction: discord.Interaction, year: int = 0, month: int = 0):
        from bigtree.modules.gpose_contest import get_weekly_winners_for_month

        now = _time.localtime()
        if year == 0:
            year = now.tm_year
        if month == 0:
            month = now.tm_mon

        winners = get_weekly_winners_for_month(year, month)
        ready = len(winners) >= 4

        embed = discord.Embed(
            title=f"📅 {year}-{month:02d} Monthly Check",
            description=f"Weekly winners: **{len(winners)}/4**",
            color=0x2ECC71 if ready else 0xF39C12,
        )
        embed.add_field(name="Ready for monthly vote", value="✅ Yes" if ready else "❌ No — need 4 weeks", inline=False)
        for w in winners:
            embed.add_field(name=f"Week {w.get('week')}", value=f"<@{w.get('user_id')}>", inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(GposeCog(bot))