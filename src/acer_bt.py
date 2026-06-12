from evdev import ecodes as k
from .bind_evdev import Bind
from .my_presets import numpad_shortcuts

bind = Bind(
    name='BT5.0 Keyboard',
    remap={
        k.KEY_RIGHTMETA: k.KEY_RIGHTCTRL,
        k.KEY_INSERT: k.KEY_SYSRQ,
    },
    regrab_on_bluetooth_reconnection=True,
)

bind.import_preset(numpad_shortcuts)

bind.serve()
