"""Discord control surface for Verdant Conclave.

Game play is hard-bound to the session's Discord channel.  Secret roles and
night actions are only returned in ephemeral interactions; the public panel
contains only information that every player is allowed to know.
"""
from __future__ import annotations

import asyncio
import re
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

import bigtree
from bigtree.games.conclave import engine
from bigtree.games.conclave.store import ConclaveStore
from bigtree.inc.logging import logger
from bigtree.inc import access_control
from bigtree.modules.permissions import requires_capability


def _phase_label(phase: str) -> str:
    return {
        engine.PHASE_LOBBY: "Gathering",
        engine.PHASE_NIGHT: "Night",
        engine.PHASE_DAY: "Dawn Council",
        engine.PHASE_NOMINATION: "Nominations",
        engine.PHASE_TRIAL: "Trial / Defence",
        engine.PHASE_JUDGEMENT: "Judgement",
        engine.PHASE_ENDED: "Ended",
    }.get(str(phase), str(phase).title())


def _phase_guidance(state: dict) -> str:
    phase = state.get("phase")
    if phase == engine.PHASE_LOBBY:
        return "Join the gathering. The host starts once at least five elves are present. Roles remain secret."
    if phase == engine.PHASE_NIGHT:
        return "Night roles choose their targets privately with **My role / action**. The host advances when ready."
    if phase == engine.PHASE_DAY:
        return "Discuss what happened during the night. When discussion is complete, the host opens nominations."
    if phase == engine.PHASE_NOMINATION:
        return "Living players use **Vote / nominate**. A strict majority immediately calls one elf to trial."
    if phase == engine.PHASE_TRIAL:
        return "The accused may make their defence. The host opens judgement when the defence is complete."
    if phase == engine.PHASE_JUDGEMENT:
        return "Living players except the accused cast a private guilty, innocent, or abstain judgement."
    winner = state.get("winner")
    if winner == engine.FACTION_CONCORD:
        return "🌿 **The Concord has prevailed.**"
    if winner == engine.FACTION_THORNBOUND:
        return "🥀 **The Thornbound have seized the Conclave.**"
    return "The Conclave is closed."


def build_public_embed(state: dict) -> discord.Embed:
    public = engine.public_state(state)
    phase = public.get("phase")
    colour = discord.Colour.from_rgb(52, 112, 74)
    if phase == engine.PHASE_NIGHT:
        colour = discord.Colour.from_rgb(61, 67, 112)
    elif phase in {engine.PHASE_TRIAL, engine.PHASE_JUDGEMENT}:
        colour = discord.Colour.from_rgb(146, 104, 45)
    elif phase == engine.PHASE_ENDED:
        colour = discord.Colour.from_rgb(87, 87, 87)

    title = public.get("title") or "Verdant Conclave"
    embed = discord.Embed(
        title=f"🌿 {title}",
        description=f"**{_phase_label(str(phase))}**\n{_phase_guidance(state)}",
        colour=colour,
    )

    players = public.get("players") or []
    lines = []
    accused = int(public.get("on_trial") or 0)
    for p in players:
        uid = int(p.get("user_id") or 0)
        alive = bool(p.get("alive", True))
        synthetic = bool(p.get("synthetic"))
        marker = "🌱" if alive else "🍂"
        trial = " ⚖️" if uid == accused else ""
        role = f" — {p.get('role')}" if p.get("role") else ""
        identity = f"🧪 {p.get('display_name') or 'Test Elf'}" if synthetic else f"<@{uid}>"
        lines.append(f"{marker} {identity}{trial}{role}")
    embed.add_field(
        name=f"Gathered elves · {sum(1 for p in players if p.get('alive', True))}/{len(players)} living",
        value="\n".join(lines) if lines else "No one has joined yet.",
        inline=False,
    )

    roster = public.get("role_roster") or []
    if roster:
        roster_lines = []
        for entry in roster:
            sigil = "🥀" if entry.get("faction") == engine.FACTION_THORNBOUND else "🌿"
            roster_lines.append(f"{sigil} {entry.get('name')} ×{int(entry.get('count') or 0)}")
        embed.add_field(name="Callings in this Conclave", value="\n".join(roster_lines)[:1024], inline=False)

    ready = public.get("readiness") or {}
    required = int(ready.get("required") or 0)
    if required:
        embed.add_field(
            name="Readiness",
            value=f"**{int(ready.get('ready') or 0)} / {required}** required choices received.",
            inline=False,
        )

    events = [str(x) for x in (public.get("public_events") or []) if str(x).strip()]
    if events:
        embed.add_field(name="The boughs whisper", value="\n".join(events[-4:])[:1024], inline=False)

    if public.get("test_mode"):
        embed.add_field(
            name="🧪 Test circle",
            value=f"{int(public.get('test_player_count') or 0)} synthetic elf/elves are present. They are not Discord users and never receive secret messages.",
            inline=False,
        )

    embed.set_footer(
        text=f"Session {public.get('game_id')} · Discord-channel locked · Host {public.get('host_user_id')}"
    )
    return embed


def build_private_embed(state: dict, user_id: int) -> discord.Embed:
    info = engine.private_player_state(state, user_id)
    if not info.get("role_name"):
        return discord.Embed(
            title="🌿 Your place in the Conclave",
            description="Your role will be revealed when the host starts the game.",
            colour=discord.Colour.green(),
        )
    faction_label = "The Concord" if info.get("faction") == engine.FACTION_CONCORD else "The Thornbound"
    embed = discord.Embed(
        title=f"🌿 {info.get('role_name')}",
        description=str(info.get("description") or ""),
        colour=discord.Colour.green() if info.get("faction") == engine.FACTION_CONCORD else discord.Colour.dark_red(),
    )
    embed.add_field(name="Allegiance", value=faction_label, inline=False)
    allies = info.get("allies") or []
    if allies:
        embed.add_field(name="Known Thornbound", value=", ".join(allies), inline=False)
    notes = info.get("notes") or []
    if notes:
        embed.add_field(
            name="Private revelations",
            value="\n".join(f"• {n.get('text')}" for n in notes[-5:])[:1024],
            inline=False,
        )
    will = str(info.get("last_will") or "").strip()
    if will:
        embed.add_field(name="Your last will", value=will[:1024], inline=False)
    if state.get("phase") == engine.PHASE_NIGHT and info.get("ability"):
        embed.add_field(
            name="Night choice",
            value="✅ Recorded — you can change it before resolution." if info.get("night_choice_recorded") else "⏳ Waiting for your choice.",
            inline=False,
        )
    if not info.get("alive"):
        embed.set_footer(text="You have fallen and may no longer act or vote.")
    elif state.get("phase") == engine.PHASE_NIGHT and info.get("ability"):
        embed.set_footer(text="Choose a target or intentionally pass. You may change the choice until night resolves.")
    else:
        embed.set_footer(text="Secret information — this panel is visible only to you.")
    return embed


class _TargetSelect(discord.ui.Select):
    def __init__(self, cog: "ConclaveCog", state: dict, actor_id: int, mode: str):
        self.cog = cog
        self.actor_id = int(actor_id)
        self.mode = mode
        if mode == "night":
            targets = engine.valid_night_targets(state, actor_id)
            placeholder = "Choose your night target…"
        else:
            targets = engine.valid_nomination_targets(state, actor_id)
            placeholder = "Choose an elf to nominate…"
        options = [
            discord.SelectOption(
                label=str(p.get("display_name") or p.get("user_id"))[:100],
                value=str(p.get("user_id")),
            )
            for p in targets[:25]
        ]
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.channel_id is None or interaction.user.id != self.actor_id:
            return await interaction.response.send_message("This private choice is not yours.", ephemeral=True)
        try:
            target_id = int(self.values[0])
            if self.mode == "night":
                await self.cog.mutate_channel(
                    interaction.channel_id,
                    lambda state: engine.submit_night_action(state, self.actor_id, target_id),
                )
                message = "🌙 Your night choice has been recorded privately."
            else:
                await self.cog.mutate_channel(
                    interaction.channel_id,
                    lambda state: engine.submit_nomination(state, self.actor_id, target_id),
                )
                message = "⚖️ Your nomination has been recorded."
            await interaction.response.edit_message(content=message, embed=None, view=None)
            await self.cog.refresh_channel_panel(interaction.channel_id)
        except engine.GameError as exc:
            await interaction.response.edit_message(content=f"❌ {exc}", embed=None, view=None)


class _PassChoiceButton(discord.ui.Button):
    def __init__(self, cog: "ConclaveCog", actor_id: int, mode: str):
        label = "Pass this night" if mode == "night" else "Nominate no one"
        emoji = "🌙" if mode == "night" else "🍃"
        super().__init__(label=label, emoji=emoji, style=discord.ButtonStyle.secondary, row=1)
        self.cog = cog
        self.actor_id = int(actor_id)
        self.mode = mode

    async def callback(self, interaction: discord.Interaction):
        if interaction.channel_id is None or interaction.user.id != self.actor_id:
            return await interaction.response.send_message("This private choice is not yours.", ephemeral=True)
        try:
            if self.mode == "night":
                await self.cog.mutate_channel(
                    interaction.channel_id,
                    lambda state: engine.submit_night_pass(state, self.actor_id),
                )
                message = "🌙 You intentionally passed your night action."
            else:
                await self.cog.mutate_channel(
                    interaction.channel_id,
                    lambda state: engine.submit_nomination_pass(state, self.actor_id),
                )
                message = "🍃 You chose not to nominate anyone this round."
            await interaction.response.edit_message(content=message, embed=None, view=None)
            await self.cog.refresh_channel_panel(interaction.channel_id)
        except engine.GameError as exc:
            await interaction.response.edit_message(content=f"❌ {exc}", embed=None, view=None)


class _TargetView(discord.ui.View):
    def __init__(self, cog: "ConclaveCog", state: dict, actor_id: int, mode: str):
        super().__init__(timeout=120)
        select = _TargetSelect(cog, state, actor_id, mode)
        if select.options:
            self.add_item(select)
        self.add_item(_PassChoiceButton(cog, actor_id, mode))


class _LastWillModal(discord.ui.Modal, title="Last will"):
    will = discord.ui.TextInput(
        label="Words to reveal if you fall",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500,
        placeholder="Leave a clue, suspicion, warning, or farewell…",
    )

    def __init__(self, cog: "ConclaveCog", state: dict, actor_id: int):
        super().__init__()
        self.cog = cog
        self.actor_id = int(actor_id)
        current = engine.private_player_state(state, actor_id).get("last_will") or ""
        self.will.default = str(current)[:500]

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.channel_id is None or interaction.user.id != self.actor_id:
            return await interaction.response.send_message("This last will is not yours.", ephemeral=True)
        try:
            await self.cog.mutate_channel(
                interaction.channel_id,
                lambda state: engine.set_last_will(state, self.actor_id, str(self.will.value or "")),
            )
            await interaction.response.send_message("📜 Your last will has been sealed privately.", ephemeral=True)
        except engine.GameError as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)


class _JudgementView(discord.ui.View):
    def __init__(self, cog: "ConclaveCog", actor_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.actor_id = int(actor_id)

    async def _vote(self, interaction: discord.Interaction, verdict: str):
        if interaction.user.id != self.actor_id or interaction.channel_id is None:
            return await interaction.response.send_message("This judgement panel is not yours.", ephemeral=True)
        try:
            await self.cog.mutate_channel(
                interaction.channel_id,
                lambda state: engine.submit_judgement(state, self.actor_id, verdict),
            )
            await interaction.response.edit_message(content=f"⚖️ **{verdict.title()}** recorded privately.", view=None)
            await self.cog.refresh_channel_panel(interaction.channel_id)
        except engine.GameError as exc:
            await interaction.response.edit_message(content=f"❌ {exc}", view=None)

    @discord.ui.button(label="Guilty", style=discord.ButtonStyle.danger)
    async def guilty(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await self._vote(interaction, "guilty")

    @discord.ui.button(label="Innocent", style=discord.ButtonStyle.success)
    async def innocent(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await self._vote(interaction, "innocent")

    @discord.ui.button(label="Abstain", style=discord.ButtonStyle.secondary)
    async def abstain(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await self._vote(interaction, "abstain")


class ConclavePanel(discord.ui.View):
    """One persistent view works for every session; channel id selects state."""

    def __init__(self, cog: "ConclaveCog"):
        super().__init__(timeout=None)
        self.cog = cog

    async def _state(self, interaction: discord.Interaction) -> Optional[dict]:
        if interaction.channel_id is None:
            return None
        return await self.cog.get_channel_state(interaction.channel_id)

    @discord.ui.button(label="Join", emoji="🌱", style=discord.ButtonStyle.success, custom_id="conclave:join", row=0)
    async def join(self, interaction: discord.Interaction, _button: discord.ui.Button):
        try:
            state = await self.cog.mutate_channel(
                interaction.channel_id,
                lambda s: engine.add_player(s, interaction.user.id, interaction.user.display_name),
            )
            await interaction.response.send_message("🌱 You joined the Verdant Conclave.", ephemeral=True)
            await self.cog.refresh_panel_from_interaction(interaction, state)
        except engine.GameError as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)

    @discord.ui.button(label="Leave", emoji="🍂", style=discord.ButtonStyle.secondary, custom_id="conclave:leave", row=0)
    async def leave(self, interaction: discord.Interaction, _button: discord.ui.Button):
        try:
            state = await self.cog.mutate_channel(
                interaction.channel_id,
                lambda s: engine.remove_player(s, interaction.user.id),
            )
            await interaction.response.send_message("You left the gathering.", ephemeral=True)
            await self.cog.refresh_panel_from_interaction(interaction, state)
        except engine.GameError as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)

    @discord.ui.button(label="My role / action", emoji="🌙", style=discord.ButtonStyle.primary, custom_id="conclave:role", row=0)
    async def role(self, interaction: discord.Interaction, _button: discord.ui.Button):
        state = await self._state(interaction)
        if not state:
            return await interaction.response.send_message("This Conclave is no longer active.", ephemeral=True)
        try:
            info = engine.private_player_state(state, interaction.user.id)
        except engine.GameError as exc:
            return await interaction.response.send_message(f"❌ {exc}", ephemeral=True)
        view = None
        if state.get("phase") == engine.PHASE_NIGHT and info.get("alive") and info.get("ability"):
            candidate_view = _TargetView(self.cog, state, interaction.user.id, "night")
            if candidate_view.children:
                view = candidate_view
        await interaction.response.send_message(embed=build_private_embed(state, interaction.user.id), view=view, ephemeral=True)

    @discord.ui.button(label="Vote / nominate", emoji="⚖️", style=discord.ButtonStyle.primary, custom_id="conclave:vote", row=0)
    async def vote(self, interaction: discord.Interaction, _button: discord.ui.Button):
        state = await self._state(interaction)
        if not state:
            return await interaction.response.send_message("This Conclave is no longer active.", ephemeral=True)
        p = engine.player(state, interaction.user.id)
        if not p or not p.get("alive"):
            return await interaction.response.send_message("Only living players may vote.", ephemeral=True)
        if state.get("phase") == engine.PHASE_NOMINATION:
            view = _TargetView(self.cog, state, interaction.user.id, "nomination")
            return await interaction.response.send_message("Choose one living elf to nominate, or deliberately nominate no one.", view=view, ephemeral=True)
        if state.get("phase") == engine.PHASE_JUDGEMENT:
            return await interaction.response.send_message(
                "Cast your private judgement.", view=_JudgementView(self.cog, interaction.user.id), ephemeral=True
            )
        await interaction.response.send_message("Voting is not open in this phase.", ephemeral=True)

    @discord.ui.button(label="Last will", emoji="📜", style=discord.ButtonStyle.secondary, custom_id="conclave:will", row=0)
    async def last_will(self, interaction: discord.Interaction, _button: discord.ui.Button):
        state = await self._state(interaction)
        if not state:
            return await interaction.response.send_message("This Conclave is no longer active.", ephemeral=True)
        try:
            info = engine.private_player_state(state, interaction.user.id)
            if not info.get("alive"):
                raise engine.GameError("A fallen elf can no longer change their last will.", "dead")
            await interaction.response.send_modal(_LastWillModal(self.cog, state, interaction.user.id))
        except engine.GameError as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)

    @discord.ui.button(label="Refresh", emoji="🔄", style=discord.ButtonStyle.secondary, custom_id="conclave:refresh", row=1)
    async def refresh(self, interaction: discord.Interaction, _button: discord.ui.Button):
        state = await self._state(interaction)
        if not state:
            return await interaction.response.send_message("This Conclave is no longer active.", ephemeral=True)
        await interaction.response.edit_message(embed=build_public_embed(state), view=self)

    @discord.ui.button(label="Start", style=discord.ButtonStyle.success, custom_id="conclave:start", row=1)
    async def start(self, interaction: discord.Interaction, _button: discord.ui.Button):
        state = await self._state(interaction)
        if not state or not self.cog.is_host_or_operator(interaction, state):
            return await interaction.response.send_message("Only the host may start this Conclave.", ephemeral=True)
        try:
            state = await self.cog.mutate_channel(interaction.channel_id, engine.start_game)
            await interaction.response.send_message("🌙 Roles have been dealt privately. Night has begun.", ephemeral=True)
            await self.cog.refresh_panel_from_interaction(interaction, state)
        except engine.GameError as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)

    @discord.ui.button(label="Advance", style=discord.ButtonStyle.primary, custom_id="conclave:advance", row=1)
    async def advance(self, interaction: discord.Interaction, _button: discord.ui.Button):
        state = await self._state(interaction)
        if not state or not self.cog.is_host_or_operator(interaction, state):
            return await interaction.response.send_message("Only the host may advance the Conclave.", ephemeral=True)
        try:
            state = await self.cog.mutate_channel(interaction.channel_id, engine.advance_phase)
            await interaction.response.send_message(f"Advanced to **{_phase_label(state.get('phase'))}**.", ephemeral=True)
            await self.cog.refresh_panel_from_interaction(interaction, state)
        except engine.GameError as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)

    @discord.ui.button(label="End", style=discord.ButtonStyle.danger, custom_id="conclave:end", row=1)
    async def end(self, interaction: discord.Interaction, _button: discord.ui.Button):
        state = await self._state(interaction)
        if not state or not self.cog.is_host_or_operator(interaction, state):
            return await interaction.response.send_message("Only the host may end this Conclave.", ephemeral=True)
        state = await self.cog.mutate_channel(interaction.channel_id, engine.end_game)
        await interaction.response.send_message("The Verdant Conclave has been closed.", ephemeral=True)
        await self.cog.refresh_panel_from_interaction(interaction, state)


class ConclaveCog(commands.Cog, name="VerdantConclave"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.store = ConclaveStore()
        self.panel = ConclavePanel(self)
        self._restored = False

    async def cog_load(self):
        self.bot.add_view(self.panel)

    async def get_channel_state(self, channel_id: int) -> Optional[dict]:
        return await asyncio.to_thread(self.store.get_active_by_channel, int(channel_id))

    async def mutate_channel(self, channel_id: int, mutator) -> dict:
        return await asyncio.to_thread(self.store.mutate_active_channel, int(channel_id), mutator)

    async def mutate_game(self, game_id: str, mutator) -> dict:
        return await asyncio.to_thread(self.store.mutate, game_id, mutator)

    def is_host_or_operator(self, interaction: discord.Interaction, state: dict) -> bool:
        if int(state.get("host_user_id") or 0) == int(interaction.user.id):
            return True
        decision = access_control.evaluate_discord_member(
            interaction.user,
            "game.conclave.host",
            resource_type="game",
            resource_id=state.get("game_id") or "",
            ancestors=[
                {"type": "channel", "id": str(state.get("channel_id") or "")},
                {"type": "guild", "id": str(state.get("guild_id") or "")},
            ],
        )
        return bool(decision.allowed)

    def _panel_view_for_state(self, state: dict):
        # Remove controls from completed games. Reusing the one persistent view
        # object for active sessions keeps restart restoration cheap.
        return None if state.get("phase") == engine.PHASE_ENDED else self.panel

    async def refresh_panel_from_interaction(self, interaction: discord.Interaction, state: dict) -> None:
        message = interaction.message
        if message:
            try:
                await message.edit(embed=build_public_embed(state), view=self._panel_view_for_state(state))
                return
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass
        if interaction.channel_id:
            await self.refresh_channel_panel(interaction.channel_id, state)

    async def refresh_channel_panel(self, channel_id: int, state: Optional[dict] = None) -> None:
        state = state or await self.get_channel_state(channel_id)
        if not state:
            return
        message_id = state.get("panel_message_id")
        if not message_id:
            return
        channel = self.bot.get_channel(int(channel_id))
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(int(channel_id))
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return
        try:
            message = await channel.fetch_message(int(message_id))
            await message.edit(embed=build_public_embed(state), view=self._panel_view_for_state(state))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            logger.warning("[conclave] unable to refresh panel game=%s channel=%s", state.get("game_id"), channel_id)

    async def refresh_game_panel(self, game_id: str, state: Optional[dict] = None) -> None:
        state = state or await asyncio.to_thread(self.store.get, game_id)
        if state and state.get("channel_id"):
            await self.refresh_channel_panel(int(state["channel_id"]), state)

    async def recreate_game_panel(self, game_id: str) -> dict:
        state = await asyncio.to_thread(self.store.get, game_id)
        if not state or not state.get("channel_id"):
            raise engine.GameError("Conclave session or bound channel not found.", "not_found")
        channel = self.bot.get_channel(int(state["channel_id"]))
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(int(state["channel_id"]))
            except (discord.NotFound, discord.Forbidden, discord.HTTPException) as exc:
                raise engine.GameError(f"Bound Discord channel is unavailable: {exc}", "channel_unavailable") from exc
        try:
            message = await channel.send(embed=build_public_embed(state), view=self._panel_view_for_state(state))
            state = await asyncio.to_thread(self.store.set_panel_message, state["game_id"], message.id)
            await message.edit(embed=build_public_embed(state), view=self._panel_view_for_state(state))
            return state
        except (discord.Forbidden, discord.HTTPException) as exc:
            raise engine.GameError(f"Discord rejected the Conclave panel: {exc}", "panel_failed") from exc

    @commands.Cog.listener()
    async def on_ready(self):
        if self._restored:
            return
        self._restored = True
        try:
            active = await asyncio.to_thread(self.store.list_active, 100)
            for state in active:
                if state.get("panel_message_id") and state.get("channel_id"):
                    await self.refresh_channel_panel(int(state["channel_id"]), state)
            logger.info("[conclave] restored %s active Discord panel(s)", len(active))
        except Exception as exc:
            logger.warning("[conclave] panel restore failed: %s", exc)

    @app_commands.command(name="conclave-create", description="Create a channel-locked Verdant Conclave social-deduction game.")
    @app_commands.describe(
        title="Name shown on the game panel",
        channel="Bind to an existing text channel instead of creating a dedicated one",
        use_current_channel="Use the channel where this command is run",
    )
    @app_commands.guilds(discord.Object(id=int(bigtree.guildid)))
    @requires_capability("game.conclave.host")
    async def create_conclave(
        self,
        interaction: discord.Interaction,
        title: str = "Verdant Conclave",
        channel: Optional[discord.TextChannel] = None,
        use_current_channel: bool = False,
    ):
        if not interaction.guild or not interaction.channel:
            return await interaction.response.send_message("This game can only be created inside the server.", ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)

        created_channel: Optional[discord.TextChannel] = None
        target_channel = channel or interaction.channel
        bind_existing = bool(channel is not None or use_current_channel)
        if channel is not None and int(channel.guild.id) != int(interaction.guild.id):
            return await interaction.followup.send("The selected channel must belong to this Discord server.", ephemeral=True)
        if not bind_existing:
            slug = re.sub(r"[^a-z0-9-]+", "-", title.lower()).strip("-") or "verdant-conclave"
            slug = slug[:70]
            try:
                category = getattr(interaction.channel, "category", None)
                created_channel = await interaction.guild.create_text_channel(
                    f"{slug}-{str(interaction.id)[-4:]}",
                    category=category,
                    topic="Verdant Conclave · channel-locked social deduction · managed by TheBigTree",
                    reason=f"Verdant Conclave created by {interaction.user}",
                )
                target_channel = created_channel
            except (discord.Forbidden, discord.HTTPException) as exc:
                return await interaction.followup.send(
                    f"I could not create the dedicated game channel: {exc}", ephemeral=True
                )

        state: Optional[dict] = None
        try:
            state = await asyncio.to_thread(
                self.store.create,
                title=title,
                guild_id=interaction.guild.id,
                channel_id=target_channel.id,
                host_user_id=interaction.user.id,
                dedicated_channel=not bind_existing,
            )
            try:
                principal_id, _ = access_control.ensure_discord_principal(interaction.user)
                if principal_id:
                    access_control.assign_role(
                        principal_id,
                        "conclave_host",
                        resource_type="game",
                        resource_id=state["game_id"],
                        source="conclave-create",
                    )
            except Exception as exc:
                logger.warning("[conclave] unable to persist resource host assignment: %s", exc)
            panel_message = await target_channel.send(embed=build_public_embed(state), view=self.panel)
            state = await asyncio.to_thread(self.store.set_panel_message, state["game_id"], panel_message.id)
            await panel_message.edit(embed=build_public_embed(state), view=self.panel)
            logger.info(
                "[conclave] created game=%s channel=%s host=%s dedicated=%s",
                state.get("game_id"),
                target_channel.id,
                interaction.user.id,
                not bind_existing,
            )
            channel_note = (
                "Existing channel bound; current channel members are not auto-enrolled and join with the **Join** button."
                if bind_existing else
                "A dedicated channel was created; players join with the **Join** button."
            )
            await interaction.followup.send(
                f"🌿 Verdant Conclave created in {target_channel.mention}. Game actions are locked to that channel. {channel_note}",
                ephemeral=True,
            )
        except Exception as exc:
            if state and state.get("game_id"):
                try:
                    await asyncio.to_thread(
                        self.store.mutate,
                        state["game_id"],
                        lambda s: engine.end_game(s, "setup_failed"),
                    )
                except Exception:
                    logger.exception("[conclave] unable to close failed setup game=%s", state.get("game_id"))
            if created_channel is not None:
                try:
                    await created_channel.delete(reason="Verdant Conclave setup failed")
                except Exception:
                    pass
            logger.exception("[conclave] creation failed")
            await interaction.followup.send(f"Could not create the Conclave: {exc}", ephemeral=True)


    @app_commands.command(name="conclave-panel", description="Recreate the control panel for the active Conclave in this channel.")
    @app_commands.guilds(discord.Object(id=int(bigtree.guildid)))
    @requires_capability("game.conclave.host")
    async def recreate_conclave_panel(self, interaction: discord.Interaction):
        if interaction.channel_id is None or interaction.channel is None:
            return await interaction.response.send_message("Use this inside the Conclave channel.", ephemeral=True)
        state = await self.get_channel_state(interaction.channel_id)
        if not state:
            return await interaction.response.send_message("There is no active Conclave in this channel.", ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            await self.recreate_game_panel(state["game_id"])
            await interaction.followup.send("🌿 The Conclave panel has been recreated in this channel.", ephemeral=True)
        except engine.GameError as exc:
            await interaction.followup.send(f"I could not recreate the panel: {exc}", ephemeral=True)



async def setup(bot: commands.Bot):
    await bot.add_cog(ConclaveCog(bot))
