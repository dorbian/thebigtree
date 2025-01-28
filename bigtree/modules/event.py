import bigtree
import discord
from discord.ext import commands
from datetime import datetime, timezone, timedelta
import requests
from PIL import Image

async def create_event(guild, starttime, eventtitle, endtime, imageloc, eventloc, partakeid, edescription, etype):
    guild = guild
    await guild.create_scheduled_event(
        name=eventtitle,
        entity_type=etype,
        description=edescription,
        start_time=starttime,
        end_time=endtime,
        image=imageloc,
        location=eventloc,
        privacy_level=discord.PrivacyLevel.guild_only,
        reason=str(partakeid)
        )
    bigtree.loch.logger.info('Event: {0} registered'.format(eventtitle))
    return True

async def create_partake_event(guild, data, uri):                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   
    event_current_date = datetime.today()
    guild = guild
    event_type=discord.EntityType.external
    event_id = data['event']['id']
    event_title = data['event']['title']
    # Check if event exists before parsing the rest and downloading data
    events = await guild.fetch_scheduled_events()
    for existing in events:
        if existing.name == event_title and existing.creator.name == 'TheBigTree':
            return False
    # process if not returned
    event_age = data['event']['ageRating']
    event_starts = datetime.fromisoformat(data['event']['startsAt'][:-1] + '+00:00')
    if datetime.now() > datetime.fromisoformat(data['event']['startsAt'][:-1]):
        now = datetime.now() - timedelta(minutes=58)
        event_starts = datetime.fromisoformat(now.strftime("%Y-%m-%d %H:%M:%S") + '+00:00')
    event_ends = datetime.fromisoformat(data['event']['endsAt'][:-1] + '+00:00')
    event_location = data['event']['location']
    event_description = data['event']['description']
    event_attachements = data['event']['attachments'][0]
    event_location = '{0}-{1}'.format(data['event']['locationData']['dataCenter']['name'], data['event']['locationData']['server']['name'])
    event_content = 'Location: {0}\nAge: {1}\nLink: {2}\n\n{3}'.format(event_location, event_age, uri, event_description)[:1000]
    # download image
    image_resize = Image.open(requests.get('https://cdn.partyverse.app/attachments/{0}'.format(event_attachements), stream=True).raw)
    image_resize.save('/tmp/image.png', quality=95, optimize=True)
    image_send = open('/tmp/image.png', 'rb')
    event_image = image_send.read()
    image_send.close()
    await create_event(guild, event_starts, event_title, event_ends, event_image, event_location, event_id, event_content, event_type)
    return True