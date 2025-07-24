import bigtree
import discord
from discord.ext import commands
from datetime import datetime, timezone, timedelta
import requests
import json
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
    # Debug: Log the entire data structure
    bigtree.loch.logger.debug(f"Full Partake API response:\n{json.dumps(data, indent=2)}")
    
    try:
        # Debug: Log basic event info
        bigtree.loch.logger.debug(f"Processing event ID: {data.get('event', {}).get('id')}")
        bigtree.loch.logger.debug(f"Event title: {data.get('event', {}).get('title')}")
        
        event_current_date = datetime.today()
        event_type = discord.EntityType.external
        event_id = data['event']['id']
        event_title = data['event']['title']
        
        # Debug: Log event time data
        bigtree.loch.logger.debug(f"Start time raw: {data['event']['startsAt']}")
        bigtree.loch.logger.debug(f"End time raw: {data['event']['endsAt']}")
        
        # Check if event exists
        events = await guild.fetch_scheduled_events()
        for existing in events:
            if existing.name == event_title and existing.creator.name == 'TheBigTree':
                bigtree.loch.logger.debug(f"Event already exists: {event_title}")
                return False
                
        # Process event details
        event_age = data['event']['ageRating']
        event_starts = datetime.fromisoformat(data['event']['startsAt'][:-1] + '+00:00')
        
        # Debug: Log processed times
        bigtree.loch.logger.debug(f"Processed start time: {event_starts}")
        
        if datetime.now() > datetime.fromisoformat(data['event']['startsAt'][:-1]):
            now = datetime.now() - timedelta(minutes=58)
            event_starts = datetime.fromisoformat(now.strftime("%Y-%m-%d %H:%M:%S") + '+00:00')
            bigtree.loch.logger.debug(f"Adjusted start time (past event): {event_starts}")
            
        event_ends = datetime.fromisoformat(data['event']['endsAt'][:-1] + '+00:00')
        event_description = data['event']['description']
        
        # Debug: Log location data
        bigtree.loch.logger.debug(f"Raw location: {data['event']['location']}")
        bigtree.loch.logger.debug(f"Location data: {data['event']['locationData']}")
        
        event_location = '{0}-{1}'.format(
            data['event']['locationData']['dataCenter']['name'],
            data['event']['locationData']['server']['name']
        )
        
        event_content = 'Location: {0}\nAge: {1}\nLink: {2}\n\n{3}'.format(
            event_location, event_age, uri, event_description
        )[:1000]
        
        # Debug: Log attachments
        attachments = data['event'].get('attachments', [])
        bigtree.loch.logger.debug(f"Found {len(attachments)} attachments: {attachments}")
        
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
        
        # Process attachments
        if attachments:
            for i, attachment_id in enumerate(attachments, 1):
                try:
                    attachment_url = f"https://cdn.partake.gg/assets/{attachment_id}"
                    bigtree.loch.logger.debug(f"Processing attachment {i}/{len(attachments)}: {attachment_url}")
                    
                    response = requests.get(attachment_url, stream=True)
                    response.raise_for_status()
                    
                    # Check content type - now including WebP
                    content_type = response.headers.get('Content-Type', '').lower()
                    bigtree.loch.logger.debug(f"Attachment content type: {content_type}")
                    
                    if not any(ct in content_type for ct in ['image/jpeg', 'image/png', 'image/webp']):
                        bigtree.loch.logger.debug(f"Skipping non-image attachment: {content_type}")
                        continue
                        
                    # Verify image - now with WebP support
                    try:
                        with Image.open(response.raw) as img:
                            # Convert WebP to PNG if needed (Discord prefers PNG)
                            if img.format == 'WEBP':
                                bigtree.loch.logger.debug("Converting WebP to PNG")
                                buffer = io.BytesIO()
                                img.save(buffer, format='PNG')
                                buffer.seek(0)
                                event_kwargs['imageloc'] = buffer.read()
                            else:
                                buffer = io.BytesIO()
                                img.save(buffer, format=img.format)
                                buffer.seek(0)
                                event_kwargs['imageloc'] = buffer.read()
                        
                        bigtree.loch.logger.debug(f"Successfully used {img.format} image: {attachment_id}")
                        break
                        
                    except Exception as img_error:
                        bigtree.loch.logger.debug(f"Attachment {attachment_id} failed image validation: {img_error}")
                        continue
                        
                except requests.exceptions.RequestException as req_error:
                    bigtree.loch.logger.debug(f"Failed to download attachment {attachment_id}: {req_error}")
                    continue

        bigtree.loch.logger.debug("No valid image attachments found" if not attachments else "Finished processing attachments")
            
        await create_event(**event_kwargs)
        bigtree.loch.logger.info(f"Successfully created event: {event_title}")
        return True
        
    except Exception as e:
        bigtree.loch.logger.error(f"Error processing Partake event: {e}\nFull data: {data}")
        return False