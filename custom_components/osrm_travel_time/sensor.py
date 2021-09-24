"""Support for osrm_travel_time sensors."""
from datetime import timedelta
import logging
from typing import Callable, Dict, Optional, Union, List
import re

import osrm
import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import (
    ATTR_ATTRIBUTION,
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    CONF_MODE,
    CONF_NAME,
    CONF_UNIT_SYSTEM,
    CONF_UNIT_SYSTEM_IMPERIAL,
    CONF_UNIT_SYSTEM_METRIC,
    TIME_MINUTES
)
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import location
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity

_LOGGER = logging.getLogger(__name__)

CONF_DESTINATION_LATITUDE = "destination_latitude"
CONF_DESTINATION_LONGITUDE = "destination_longitude"
CONF_DESTINATION_ENTITY_ID = "destination_entity_id"
CONF_DESTINATION_NAME = "destination_name"
CONF_ORIGIN_LATITUDE = "origin_latitude"
CONF_ORIGIN_LONGITUDE = "origin_longitude"
CONF_ORIGIN_ENTITY_ID = "origin_entity_id"
CONF_ORIGIN_NAME = "origin_name"
CONF_SERVER_ADDR = "server"
CONF_MODE = "profile"
CONF_SHOW_ROUTE = "show_route"

DEFAULT_NAME = "OSRM Travel Time"
ATTRIBUTION = "Powered by Open Source Routing Machine"

TRAVEL_MODE_BICYCLE = "^(bike|bicycle)(\-\S+)*$"
TRAVEL_MODE_CAR = "^(car|auto)(\-\S+)*$"
TRAVEL_MODE_PEDESTRIAN = "^(foot|walk)(\-\S+)*$"

SHOW_ROUTE_FULL = "full"
SHOW_ROUTE_SUMMARY = "summary"
SHOW_ROUTE_NONE = "none"
SHOW_ROUTE = [SHOW_ROUTE_FULL, SHOW_ROUTE_SUMMARY, SHOW_ROUTE_NONE]

ICON_BICYCLE = "mdi:bike"
ICON_CAR = "mdi:car"
ICON_PEDESTRIAN = "mdi:walk"
ICON_NAVIGATION = "mdi:navigation"

UNITS = [CONF_UNIT_SYSTEM_METRIC, CONF_UNIT_SYSTEM_IMPERIAL]

ATTR_DURATION = "duration"
ATTR_DISTANCE = "distance"
ATTR_ROUTE = "route"
ATTR_ORIGIN = "origin"
ATTR_DESTINATION = "destination"
ATTR_ORIGIN_NAME = "origin_name"
ATTR_DESTINATION_NAME = "destination_name"

SCAN_INTERVAL = timedelta(minutes=5)

TRACKABLE_DOMAINS = ["device_tracker", "sensor", "zone", "person"]
DATA_KEY = "osrm_travel_time"

COORDINATE_SCHEMA = vol.Schema(
    {
        vol.Inclusive(CONF_DESTINATION_LATITUDE, "coordinates"): cv.latitude,
        vol.Inclusive(CONF_DESTINATION_LONGITUDE, "coordinates"): cv.longitude,
    }
)

PLATFORM_SCHEMA = vol.All(
    cv.has_at_least_one_key(CONF_DESTINATION_LATITUDE, CONF_DESTINATION_ENTITY_ID),
    cv.has_at_least_one_key(CONF_ORIGIN_LATITUDE, CONF_ORIGIN_ENTITY_ID),
    PLATFORM_SCHEMA.extend(
        {
            vol.Required(CONF_SERVER_ADDR): cv.string,
            vol.Inclusive(CONF_DESTINATION_LATITUDE, "destination_coordinates"): cv.latitude,
            vol.Inclusive(CONF_DESTINATION_LONGITUDE, "destination_coordinates"): cv.longitude,
            vol.Exclusive(CONF_DESTINATION_LATITUDE, "destination"): cv.latitude,
            vol.Exclusive(CONF_DESTINATION_ENTITY_ID, "destination"): cv.entity_id,
            vol.Optional(CONF_DESTINATION_NAME): cv.string,
            vol.Inclusive(CONF_ORIGIN_LATITUDE, "origin_coordinates"): cv.latitude,
            vol.Inclusive(CONF_ORIGIN_LONGITUDE, "origin_coordinates"): cv.longitude,
            vol.Exclusive(CONF_ORIGIN_LATITUDE, "origin"): cv.latitude,
            vol.Exclusive(CONF_ORIGIN_ENTITY_ID, "origin"): cv.entity_id,
            vol.Optional(CONF_ORIGIN_NAME): cv.string,
            vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
            vol.Optional(CONF_MODE, default=TRAVEL_MODE_CAR): cv.string,
            vol.Optional(CONF_SHOW_ROUTE, default=SHOW_ROUTE_SUMMARY): vol.In(SHOW_ROUTE),
            vol.Optional(CONF_UNIT_SYSTEM): vol.In(UNITS),
        }
    ),
)

async def async_setup_platform(
    hass: HomeAssistant,
    config: Dict[str, Union[str, bool]],
    async_add_entities: Callable,
    discovery_info: None = None,
) -> None:
    """Set up the osrm_travel_time platform."""
    hass.data.setdefault(DATA_KEY, [])

    server_address = config[CONF_SERVER_ADDR]
    if config.get(CONF_ORIGIN_LATITUDE) is not None:
        origin = ",".join(
            [str(config[CONF_ORIGIN_LATITUDE]), str(config[CONF_ORIGIN_LONGITUDE])]
        )
    else:
        origin = config[CONF_ORIGIN_ENTITY_ID]

    if config.get(CONF_DESTINATION_LATITUDE) is not None:
        destination = ",".join(
            [str(config[CONF_DESTINATION_LATITUDE]), str(config[CONF_DESTINATION_LONGITUDE])]
        )
    else:
        destination = config[CONF_DESTINATION_ENTITY_ID]

    if config.get(CONF_ORIGIN_NAME) is not None:
        origin_name = config.get(CONF_ORIGIN_NAME)
    else:
        origin_name = "-"

    if config.get(CONF_DESTINATION_NAME) is not None:
        destination_name = config.get(CONF_DESTINATION_NAME)
    else:
        destination_name = "-"

    travel_mode = config.get(CONF_MODE)
    show_route = config.get(CONF_SHOW_ROUTE)
    name = config.get(CONF_NAME)
    units = config.get(CONF_UNIT_SYSTEM, hass.config.units.name)

    osrm_data = OSRMTravelTimeData(
        None, None, origin_name, destination_name, server_address, travel_mode, show_route, units
    )

    sensor = OSRMTravelTimeSensor(hass, name, origin, destination, osrm_data)

    hass.data[DATA_KEY].append(sensor)

    async_add_entities([sensor], True)

class OSRMTravelTimeSensor(Entity):
    """Representation of an OSRM travel time sensor."""

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        origin: str,
        destination: str,
        osrm_data: "OSRMTravelTimeData",
    ) -> None:
        """Initialize the sensor."""
        self._hass = hass
        self._name = name
        self._osrm_data = osrm_data
        self._unit_of_measurement = TIME_MINUTES
        self._origin_entity_id = None
        self._destination_entity_id = None

        # Check if location is a trackable entity
        if origin.split(".", 1)[0] in TRACKABLE_DOMAINS:
            self._origin_entity_id = origin
        else:
            self._osrm_data.origin = origin

        if destination.split(".", 1)[0] in TRACKABLE_DOMAINS:
            self._destination_entity_id = destination
        else:
            self._osrm_data.destination = destination

    @property
    def state(self) -> Optional[str]:
        """Return the state of the sensor."""
        if self._osrm_data.duration is not None:
            return str(round(self._osrm_data.duration / 60))

        return None

    @property
    def name(self) -> str:
        """Get the name of the sensor."""
        return self._name

    @property
    def device_state_attributes(
        self
    ) -> Optional[Dict[str, Union[None, float, str, bool]]]:
        """Return the state attributes."""
        if self._osrm_data.duration is None:
            return None

        res = {ATTR_ATTRIBUTION: ATTRIBUTION}
        res[ATTR_DURATION] = round(self._osrm_data.duration / 60)
        res[ATTR_DISTANCE] = round(self._osrm_data.distance, 1)
        res[ATTR_ROUTE] = self._osrm_data.route
        res[CONF_UNIT_SYSTEM] = self._osrm_data.units
        res[ATTR_ORIGIN] = self._osrm_data.origin
        res[ATTR_DESTINATION] = self._osrm_data.destination
        res[ATTR_ORIGIN_NAME] = self._osrm_data.origin_name
        res[ATTR_DESTINATION_NAME] = self._osrm_data.destination_name
        res[CONF_MODE] = self._osrm_data.travel_mode
        return res

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit this state is expressed in."""
        return self._unit_of_measurement

    @property
    def icon(self) -> str:
        """Icon to use in the frontend depending on travel_mode."""
        if re.match(TRAVEL_MODE_BICYCLE, self._osrm_data.travel_mode):
            return ICON_BICYCLE
        if re.match(TRAVEL_MODE_PEDESTRIAN, self._osrm_data.travel_mode):
            return ICON_PEDESTRIAN
        if re.match(TRAVEL_MODE_CAR, self._osrm_data.travel_mode):
            return ICON_CAR
        return ICON_NAVIGATION

    async def async_update(self) -> None:
        """Update Sensor Information."""
        # Convert device_trackers to friendly location
        if self._origin_entity_id is not None:
            self._osrm_data.origin = await self._get_location_from_entity(
                self._origin_entity_id
            )
            self._osrm_data.origin_name = await self._get_name_from_entity(self._origin_entity_id)

        if self._destination_entity_id is not None:
            self._osrm_data.destination = await self._get_location_from_entity(
                self._destination_entity_id
            )
            self._osrm_data.destination_name = await self._get_name_from_entity(self._destination_entity_id)

        await self._hass.async_add_executor_job(self._osrm_data.update)

    async def _get_location_from_entity(self, entity_id: str) -> Optional[str]:
        """Get the location from the entity state or attributes."""
        entity = self._hass.states.get(entity_id)

        if entity is None:
            _LOGGER.error("Unable to find entity %s", entity_id)
            return None

        # Check if the entity has location attributes
        if location.has_location(entity):
            return self._get_location_from_attributes(entity)

        # Check if device is in a zone
        zone_entity = self._hass.states.get("zone.{}".format(entity.state))
        if location.has_location(zone_entity):
            _LOGGER.debug(
                "%s is in %s, getting zone location", entity_id, zone_entity.entity_id
            )
            return self._get_location_from_attributes(zone_entity)

        # If zone was not found in state then use the state as the location
        if entity_id.startswith("sensor."):
            return entity.state

    async def _get_name_from_entity(self, entity_id: str) -> str:
        """Get the name from the entity."""
        entity = self._hass.states.get(entity_id)

        if entity is None:
            _LOGGER.error("Unable to find entity %s", entity_id)
            return None
        try:
            entity_name = entity.name
        except AttributeError:
            entity_name = entity.object_id
        return entity_name

    @staticmethod
    def _get_location_from_attributes(entity: State) -> str:
        """Get the lat/long string from an entities attributes."""
        attr = entity.attributes
        return "{},{}".format(attr.get(ATTR_LATITUDE), attr.get(ATTR_LONGITUDE))

class OSRMTravelTimeData:
    """OSRMTravelTimeData data object."""

    def __init__(
        self,
        origin: None,
        destination: None,
        origin_name: str,
        destination_name: str,
        server_address: str,
        travel_mode: str,
        show_route: str,
        units: str,
    ) -> None:
        self.origin = origin
        self.destination = destination
        self.origin_name = origin_name
        self.destination_name = destination_name
        self.travel_mode = travel_mode
        self.show_route = show_route
        self.duration = None
        self.distance = None
        self.route = None
        self.base_time = None
        self.units = units
        self._client = osrm.Client(
            host=server_address,
            profile=travel_mode
        )

    def update(self) -> None:
        """Get the latest data from OSRM server"""

        if self.destination is not None and self.origin is not None:
            _LOGGER.debug(
                "Requesting route for origin: %s (%s), destination: %s (%s), show_route: %s, mode: %s",
                self.origin,
                self.origin_name,
                self.destination,
                self.destination_name,
                self.show_route,
                self.travel_mode,
            )

            coords = []
            origin_lat = float(self.origin.split(",")[0])
            origin_lon = float(self.origin.split(",")[1])
            destination_lat = float(self.destination.split(",")[0])
            destination_lon = float(self.destination.split(",")[1])
            coords.append([origin_lon,origin_lat])
            coords.append([destination_lon,destination_lat])

            show_route = self.show_route
            get_steps = bool(show_route != SHOW_ROUTE_NONE)

            directions_response = self._client.route(coordinates=coords, overview=osrm.overview.false, alternatives=False, steps=get_steps, annotations=False)

            routes = directions_response["routes"]
            summary = routes[0]["legs"][0]["summary"]
            steps = routes[0]["legs"][0]["steps"]

            self.duration = routes[0]["duration"]
            distance = routes[0]["distance"]
            if self.units == CONF_UNIT_SYSTEM_IMPERIAL:
                # Convert to miles.
                self.distance = distance / 1609.344
            else:
                # Convert to kilometers
                self.distance = distance / 1000

            if show_route == SHOW_ROUTE_FULL:
                self.route = self._get_route_from_steps(steps)
            elif show_route == SHOW_ROUTE_SUMMARY:
                self.route = summary
            else:
                self.route = "-"

    @staticmethod
    def _get_route_from_steps(steps: List[dict]) -> str:
        """Extract a route from the maneuver instructions."""
        road_names: List[str] = []

        for step in steps:
            road_name = step["name"]

            if road_name != "-":
                # Only add if it does not repeat
                if not road_names or road_names[-1] != road_name:
                    road_names.append(road_name)
        route = "; ".join(list(map(str, road_names)))
        return route