import csv
import os

filtered_entities = []

for state in hass.states.all():
    if (
        state.domain == "sensor"
        and "_percentage" in state.entity_id
        and "grid_fossil_fuel" not in state.entity_id
        and state.state not in ["unavailable", "unknown"]
    ):
        filtered_entities.append(
            {
                "friendly_name": state.attributes["friendly_name"],
                "entity_id": state.entity_id,
                "state": float(state.state) / 100,
            }
        )

csv_file_path = os.path.join(hass.config.path(), "filtered_sensors.csv")

with open(csv_file_path, "w", newline="") as csvfile:
    fieldnames = ["friendly_name", "entity_id", "state"]
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

    writer.writeheader()
    for entity in filtered_entities:
        writer.writerow(entity)
