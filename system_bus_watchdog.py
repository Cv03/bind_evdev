import asyncio
import argparse
from asyncio import Task
from typing import Protocol, cast
from dbus_next.aio.message_bus import MessageBus
from dbus_next.constants import BusType
from dbus_next.message import Message
from dbus_next.signature import Variant


name: str | None
address: str | None

_tasks = set[Task[None]]()


class SupportsGetNameAndGetAddress(Protocol):
    async def get_name(self) -> str: ...
    async def get_address(self) -> str: ...


async def disconnect_sys_bus_on_bt_keyboard_connection(
        sys_bus: MessageBus, path: str):
    introspect = await sys_bus.introspect('org.bluez', path)
    proxy_object = sys_bus.get_proxy_object('org.bluez', path, introspect)
    interface = cast(SupportsGetNameAndGetAddress, cast(
        object, proxy_object.get_interface('org.bluez.Device1')))

    if name is not None:
        device_name = await interface.get_name()
        if device_name != name:
            return

    if address is not None:
        device_address = await interface.get_address()
        if device_address != address:
            return

    sys_bus.disconnect()


async def watchdog():
    sys_bus = await MessageBus(bus_type=BusType.SYSTEM).connect()

    match_rule = "type='signal',sender='org.bluez',interface='org.freedesktop.DBus.Properties',member='PropertiesChanged'"
    _ = await sys_bus.call(
        Message(
            destination="org.freedesktop.DBus",
            path="/org/freedesktop/DBus",
            interface="org.freedesktop.DBus",
            member="AddMatch",
            signature="s",
            body=[match_rule],
        )
    )

    def message_handler(message: Message):
        body = message.body
        path = message.path

        if len(body) < 2 or body[0] != 'org.bluez.Device1':
            return

        connected_variant = cast(dict[str, Variant], body[1]).get('Connected')
        if connected_variant and cast(bool, connected_variant.value):
            task = asyncio.create_task(
                disconnect_sys_bus_on_bt_keyboard_connection(
                    sys_bus, path))
            _tasks.add(task)
            task.add_done_callback(_tasks.discard)

    sys_bus.add_message_handler(message_handler)

    await sys_bus.wait_for_disconnect()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    _ = parser.add_argument('--name')
    _ = parser.add_argument('--address')

    args = parser.parse_args()
    name = cast(str | None, args.name)
    address = cast(str | None, args.address)

    if name is None and address is None:
        raise TypeError('Supported criteria: name, address. Specify at least one.')

    if address is not None:
        # Address is uppercase as per dbus specification.
        address = address.upper()

    asyncio.run(watchdog())
