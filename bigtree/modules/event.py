import bigtree
import discord
from discord.ext import commands
from datetime import datetime, timezone, timedelta
import requests
from PIL import Image

async def create_event(guild, starttime, eventtitle, endtime, eventloc, partakeid, edescription, etype, imageloc=None):
    await guild.create_scheduled_event(
        name=eventtitle,
        entity_type=etype,
        description=edescription,
        start_time=starttime,
        end_time=endtime,
        image=imageloc,  # This can be None
        location=eventloc,
        privacy_level=discord.PrivacyLevel.guild_only,
        reason=str(partakeid)
    )
    bigtree.loch.logger.info('Event: {0} registered'.format(eventtitle))
    return True

async def create_partake_event(guild, data, uri):
    event_current_date = datetime.today()
    guild = guild
    event_type = discord.EntityType.external
    event_id = data['event']['id']
    event_title = data['event']['title']
    
    # Check if event exists
    events = await guild.fetch_scheduled_events()
    for existing in events:
        if existing.name == event_title and existing.creator.name == 'TheBigTree':
            return False
            
    # Process event details
    event_age = data['event']['ageRating']
    event_starts = datetime.fromisoformat(data['event']['startsAt'][:-1] + '+00:00')
    if datetime.now() > datetime.fromisoformat(data['event']['startsAt'][:-1]):
        now = datetime.now() - timedelta(minutes=58)
        event_starts = datetime.fromisoformat(now.strftime("%Y-%m-%d %H:%M:%S") + '+00:00')
    event_ends = datetime.fromisoformat(data['event']['endsAt'][:-1] + '+00:00')
    event_location = data['event']['location']
    event_description = data['event']['description']
    event_location = '{0}-{1}'.format(
        data['event']['locationData']['dataCenter']['name'],
        data['event']['locationData']['server']['name']
    )
    event_content = 'Location: {0}\nAge: {1}\nLink: {2}\n\n{3}'.format(
        event_location, event_age, uri, event_description
    )[:1000]
    
    # Prepare event creation kwargs
    event_kwargs = {
        'guild': guild,
        'starttime': event_starts,
        'eventtitle': event_title,
        'endtime': event_ends,
        'eventloc': event_location,
        'partakeid': event_id,
        'edescription': event_content,
        'etype': event_type
    }
    
    # Handle image attachments - check all attachments for first valid image
    event_kwargs = {
        'guild': guild,
        'starttime': event_starts,
        'eventtitle': event_title,
        'endtime': event_ends,
        'eventloc': event_location,
        'partakeid': event_id,
        'edescription': event_content,
        'etype': event_type
    }

    # Only proceed if there are attachments
    if data['event']['attachments']:
        for attachment_id in data['event']['attachments']:
            try:
                attachment_url = f"https://cdn.partyverse.app/attachments/{attachment_id}"
                response = requests.get(attachment_url, stream=True)
                response.raise_for_status()  # Check if request was successful
                
                # Verify it's an image by checking magic numbers
                image_bytes = response.content
                if image_bytes.startswith(b'\xff\xd8\xff') or image_bytes.startswith(b'\x89PNG\r\n\x1a\n'):
                    # Valid JPEG or PNG found
                    image_resize = Image.open(response.raw)
                    image_resize.verify()  # Verify it's a valid image
                    image_resize = Image.open(response.raw)  # Need to reopen after verify
                    
                    image_resize.save('/tmp/image.png', quality=95, optimize=True)
                    with open('/tmp/image.png', 'rb') as image_send:
                        event_kwargs['imageloc'] = image_send.read()
                    break  # Use first valid image found
                    
            except (requests.exceptions.RequestException, IOError, Image.UnidentifiedImageError) as e:
                bigtree.loch.logger.warning(f"Attachment {attachment_id} is not a valid image: {e}")
                continue  # Try next attachment

    await create_event(**event_kwargs)
    return True