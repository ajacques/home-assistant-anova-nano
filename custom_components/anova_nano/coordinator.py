"""DataUpdateCoordinator for anova_nano."""

from __future__ import annotations

import asyncio
import logging
import time
from asyncio import timeout
from datetime import timedelta
from typing import TYPE_CHECKING

from bleak import BLEDevice, BleakError
from bleak_retry_connector import BleakNotFoundError
from homeassistant.components import bluetooth
from homeassistant.const import UnitOfTemperature
from habluetooth import BluetoothServiceInfoBleak
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from pyanova_nano import PyAnova

from .const import DOMAIN, TIMEOUT, UPDATE_INTERVAL, NAME

if TYPE_CHECKING:
    from pyanova_nano.types import SensorValues

DEVICE_CONNECTION_TIMEOUT = 15
_UPDATE_INTERVAL = timedelta(seconds=UPDATE_INTERVAL)


class AnovaNanoDataUpdateCoordinator(DataUpdateCoordinator[None]):
    """Class to manage fetching example data."""

    def __init__(
        self,
        hass: HomeAssistant,
        logger: logging.Logger,
        entry: ConfigEntry,
    ) -> None:
        """Initialize example data coordinator."""
        super().__init__(
            hass=hass,
            logger=logger,
            name=DOMAIN,
            update_interval=None,
        )
        self.config_entry: ConfigEntry = entry
        self._hass: HomeAssistant = hass
        self._address: str = entry.data[CONF_ADDRESS]

        self._ble_device: BLEDevice | None = None
        self._client: PyAnova | None = None

        self.last_update_success: bool = False

        self._temp_units: str | None = None
        self.status: SensorValues | None = None
        self.timer: int | None = None
        self._cooking_timer_set: int | None = None
        self._last_timer_update: float | None = None
        self.target_temperature: float | None = None

    async def _connect(self):
        """Ensure the client is connected."""
        logging.getLogger("pyanova_nano.client").setLevel(self.logger.level)

        if self._client and self._client.is_connected():
            return

        self.logger.info("Connecting to %s", self._address)

        # Try to discover the device if needed.
        if not self._ble_device:
            self._ble_device = bluetooth.async_ble_device_from_address(
                self._hass, address=self._address.upper(), connectable=True
            )
            if not self._ble_device:
                # Stop polling until rediscovered.
                self.update_interval = None
                raise UpdateFailed(f"{NAME} device has not been discovered yet.")

        if not self._client:
            self._client = PyAnova(self._hass.loop, device=self._ble_device)
            self._client.add_on_disconnect(self.on_disconnect)

        # Connect client.
        if not self._client.is_connected():
            try:
                await self._client.connect(
                    device=self._ble_device,
                    timeout_seconds=DEVICE_CONNECTION_TIMEOUT,
                )
            except (TimeoutError, BleakError, BleakNotFoundError) as err:
                self.logger.debug(err, exc_info=True)
                # Stop polling until async_discovered_device was called.
                self.update_interval = None
                bluetooth.async_rediscover_address(self._hass, self._address)
                raise UpdateFailed(
                    f"Unable to connect in to {NAME} with address: {self._address}"
                ) from err

        self.update_interval = timedelta(seconds=UPDATE_INTERVAL)

    def on_disconnect(self):
        """Set to unavailable and allow rediscovery.

        Triggered if device is disconnected.

        """
        self.last_update_success = False
        self.update_interval = None

        self.async_update_listeners()
        bluetooth.async_rediscover_address(self._hass, self._address)

    async def disconnect(self):
        """Disconnect from the device (intentionally)."""
        if self._client and self._client.is_connected():
            await self._client.disconnect()

        bluetooth.async_rediscover_address(self._hass, self._address)

        # Stop updating.
        self.update_interval = None

    @property
    def client(self) -> PyAnova:
        """The API client."""
        if not self._client:
            raise UpdateFailed("Client not ready.")

        return self._client

    @callback
    def async_discovered_device(
        self,
        service_info: BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        """Subscribe to bluetooth changes."""
        self.logger.info("Discovered: %s", service_info.name)
        if service_info.address != self._address:
            return

        self._hass.async_create_task(self.async_request_refresh())

    async def _async_update_data(self) -> SensorValues:
        """Update the device status."""
        await self._connect()

        async with timeout(TIMEOUT):
            try:
                self._temp_unit_update_cooking_timer_sets = await self.client.get_unit()
                self.status = await self.client.get_sensor_values()
                new_timer = await self.client.get_timer()
                if new_timer is not None:
                    self._cooking_timer_set = self._update_cooking_timer_set(
                        new_timer,
                    )
                self.timer = new_timer
                self._last_timer_update = time.monotonic()
                self.target_temperature = await self.client.get_target_temperature()
            except Exception as err:
                self.last_update_success = False
                self.logger.debug(err, exc_info=True)
                raise UpdateFailed(err) from err

        self.last_update_success = True
        return self.status

    async def turn_on(self):
        """Start cooking."""
        await self._connect()

        try:
            await self.client.start()
        except Exception as err:  # TODO: Narrow down
            raise UpdateFailed(err) from err

        # Wait for the motor to spin up.
        await asyncio.sleep(1.0)

    async def turn_off(self):
        """Stop cooking."""
        await self._connect()

        try:
            await self.client.stop()
        except Exception as err:  # TODO: Narrow down
            raise UpdateFailed(err) from err

    def _update_cooking_timer_set(self, new_timer: int) -> int:
        """Determine the cooking_timer_set value based on the new timer reading.

        Normally the timer only counts down. If the timer increases or
        decreases by more than the elapsed time since the last update,
        the user must have changed it on the device.
        """
        if self._cooking_timer_set is None:
            return new_timer

        if self.timer is None:
            return new_timer

        elapsed_seconds = time.monotonic() - self._last_timer_update
        elapsed_minutes = elapsed_seconds / 60
        if new_timer > self.timer:
            # Sometimes, when changing the cook time on the device, the next refresh, we see n-1 minutes
            # Since the Nano only supports increments of 5 minutes, if we see a 4 minute number, we know to round up
            self.logger.debug("Remote time increase, old=%s,new=%s,delta=%s", self.timer, new_timer, elapsed_minutes)
            return new_timer

        if self._last_timer_update is not None:
            expected_max_decrease = max(1, int(elapsed_minutes) + 1)
            if self.timer - new_timer > expected_max_decrease:
                return new_timer

        return self._cooking_timer_set

    async def set_timer(self, minutes: int):
        """Set the cooking timer."""
        await self._connect()

        try:
            await self.client.set_timer(int(minutes))
        except Exception as err:  # TODO: Narrow down
            raise UpdateFailed(err) from err

        self.timer = minutes
        self._cooking_timer_set = minutes

    async def set_target_temperature(self, temp: float):
        """Set the target temperature."""
        await self._connect()

        try:
            await self.client.set_target_temperature(temp)
        except Exception as err:  # TODO: Narrow down
            raise UpdateFailed(err) from err

        self.target_temperature = temp

    @property
    def temp_units(self) -> str | None:
        """Temperature units used by the device."""
        if not self._temp_units:
            return None

        return (
            UnitOfTemperature.CELSIUS
            if self._temp_units == "C"
            else UnitOfTemperature.FAHRENHEIT
        )

    @property
    def cooking_timer_set(self) -> int | None:
        """The last user-set cooking timer value."""
        return self._cooking_timer_set
