import bigtree
import discord

class Contest(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.value = None
        self.message = None
        self.savename = None

    # When the confirm button is pressed, set the inner value to `True` and
    # stop the View from listening to more input.
    # We also send the user an ephemeral message that we're confirming their choice.
    # @discord.ui.button(label='Vote', style=discord.ButtonStyle.green)
    # async def button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
    #     contest_management(self.message.channel.id, insertdata=self.message, command="update")
    #     await interaction.response.send_message('Voting', ephemeral=True)

class MyView(discord.ui.View): 
    @discord.ui.button(label="A button", style=discord.ButtonStyle.primary) 
    async def button_callback(self, button, interaction): 
        button.disabled = True # set button.disabled to True to disable the button 
        button.label = "No more pressing!" # change the button's label to something else 
        await interaction.response.edit_message(view=self) # edit the message's view