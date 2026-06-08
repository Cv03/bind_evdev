from .bind_evdev import Bind
from .my_presets import numpad_shortcuts

bind = Bind(
    name='AT Translated Set 2 keyboard',
    remap_copilot_key=True,
)

bind.import_preset(numpad_shortcuts)

bind.serve()
