
import bigtree
from gql import gql, Client
from gql.transport.aiohttp import AIOHTTPTransport

# Select your transport with a defined url endpoint
transport = AIOHTTPTransport(url="https://api.partake.gg/")
client = Client(transport=transport, fetch_schema_from_transport=True)

# Provide a GraphQL query
def retrieve_event(eventID):
    query = gql(
        """
        query getEventName($id: Int!) { 
        event (id: $id) {id,title,locationId,ageRating,attendeeCount,startsAt,endsAt,location,tags,description(type: PLAIN_TEXT)attendeeCount,attachments,locationData {server {name},dataCenter {name}}}}
    """
    )
    eventid = {"id": int(eventID)}
    result = client.execute(query, variable_values=eventid)
    bigtree.Loch.info(result)
    return result