# Import necessary libraries
import homeassistant.helpers.script as script
hass = script.Hass()

# Define your script functions here
def get_entities(keyword):
    entities = []

    # Find all entities containing the keyword
    for entity in hass.states.all():
        if keyword in entity.entity_id:
            entities.append(entity.entity_id)

    # Return the list of found entities
    return entities
