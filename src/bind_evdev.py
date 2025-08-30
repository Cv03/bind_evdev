from collections.abc import Sequence, Callable, Iterator
from sys import stderr
from typing import Never, Literal, cast, Any, Protocol
from time import sleep
from evdev import InputEvent, KeyEvent, InputDevice, categorize, UInput, ecodes
from evdev import list_devices  # pyright: ignore[reportUnknownVariableType]


type On = Literal['raw', 'tap', 'tap_release', 'hold', 'hold_release', 'no_op']
type Shortcut = Callable[[KeyEvent], None]
type ShortcutResult = Literal['accept', 'catch', 'reject']
type Before = Sequence[Callable[[KeyEvent], ShortcutResult]]
type After = Sequence[Callable[[KeyEvent], Any]]  # pyright: ignore[reportExplicitAny]


class SupportsReadLoop(Protocol):
    def read_loop(self) -> Iterator[InputEvent]: ...


class SupportsActiveKeys(Protocol):
    def active_keys(self) -> list[int]: ...


class SupportsWrite(Protocol):
    def write(self, etype: int, code: int, value: int) -> None: ...


class SupportsSyn(Protocol):
    def syn(self) -> None: ...


class _BoundShortcut:
    def __init__(
        self,
        shortcut: Shortcut,
        *,
        on: On,
        duration: float,
        modifiers: Sequence[int],
        before: Before | None,
        after: After | None,
        bind: 'Bind'
    ):
        self._shortcut: Shortcut = shortcut
        self._on: On = on
        self._duration: float = duration
        self._modifiers: Sequence[int] = modifiers
        self._before: Before | None = before
        self._after: After | None = after
        self._bind: 'Bind' = bind
        self._fired: bool = False

    @property
    def priority(self):
        return len(self._modifiers)

    def __call__(self, e: KeyEvent) -> ShortcutResult:
        shortcut_result: ShortcutResult | None = None
        if self._modifiers_on():
            if self._before is not None:
                for fn in self._before:
                    fn_result = fn(e)
                    if fn_result != 'accept':
                        shortcut_result = fn_result
                        break
        else:
            shortcut_result = 'reject'

        if shortcut_result is None:
            fire = False
            match self._on:
                case 'raw':
                    fire = True
                case 'tap':
                    if e.keystate == KeyEvent.key_down:
                        fire = True
                        self._fired = True
                    elif e.keystate == KeyEvent.key_up and self._fired:
                        self._fired = False
                        shortcut_result = 'catch'
                case 'tap_release':
                    if (e.keystate == KeyEvent.key_up
                            and self._press_duration(e) < self._duration):
                        fire = True
                case 'hold':
                    if e.keystate == KeyEvent.key_hold:
                        if (not self._fired
                                and self._press_duration(e) > self._duration):
                            fire = True
                            self._fired = True
                    elif e.keystate == KeyEvent.key_up and self._fired:
                        self._fired = False
                        shortcut_result = 'catch'
                case 'hold_release':
                    if (e.keystate == KeyEvent.key_up
                            and self._press_duration(e) > self._duration):
                        fire = True
                case 'no_op':
                    shortcut_result = 'catch'  # Event is always catched on disabled shortcuts.

            if fire:
                shortcut_result = 'accept'
                self._shortcut(e)
            elif shortcut_result is None:
                shortcut_result = 'reject'

        if self._after is not None:
            for fn in self._after:
                _ = fn(e)  # pyright: ignore[reportAny]

        return shortcut_result

    def _press_duration(self, e: KeyEvent):
        return e.event.timestamp() - self._bind.press_history[e.scancode]

    def _modifiers_on(self):
        active_keys = cast(
            SupportsActiveKeys, self._bind.device).active_keys()
        return all(modifier in active_keys
                   for modifier in self._modifiers)


class _Stroke:
    def __init__(self) -> None:
        self.ui: UInput = UInput()

    def write_raw(self, key_code: int, event_value: int) -> None:
        cast(SupportsWrite, self.ui).write(ecodes.EV_KEY, key_code, event_value)
        cast(SupportsSyn, self.ui).syn()
        sleep(0.005)

    def write_type(self, key_code: int) -> None:
        self.write_raw(key_code, KeyEvent.key_down)
        self.write_raw(key_code, KeyEvent.key_up)

    def write_hotkey(self, *key_codes: int) -> None:
        for key_code in key_codes:
            self.write_raw(key_code, KeyEvent.key_down)
        for key_code in key_codes[::-1]:
            self.write_raw(key_code, KeyEvent.key_up)


def find_device(
    *,
    name: str | None = None,
    phys: str | None = None,
    uniq: str | None = None
) -> InputDevice:
    if name is None and phys is None and uniq is None:
        raise ValueError(
            'Specify at least one of parameters: name, phys, uniq.')

    found_devices: list[InputDevice] = []
    for path in list_devices():
        device = InputDevice(path)
        if ((name is None or device.name == name) and
            (phys is None or device.phys == phys) and
                (uniq is None or device.uniq == uniq)):
            found_devices.append(device)

    match len(found_devices):
        case 1:
            return found_devices[0]
        case 0:
            fields: list[str] = []
            if name is not None:
                fields.append(f"name='{name}'")
            if phys is not None:
                fields.append(f"phys='{phys}'")
            if uniq is not None:
                fields.append(f"uniq='{uniq}'")

            error_message = f'No such device: {', '.join(fields)}'
            raise ValueError(error_message)
        case _:
            for device in found_devices:
                device_info = (
                    f"'{cast(str, device.path)}', name={device.name}, "
                    f"phys='{device.phys}, uniq='{device.uniq}'")
                print(device_info, file=stderr)
            raise ValueError('More than one device found, add more ' +
                             'arguments so that there is only one match.')


class Bind:
    def __init__(
        self,
        *,
        name: str | None = None,
        phys: str | None = None,
        uniq: str | None = None,
        remap: dict[int, int] | None = None,
        no_pass_throuth: set[int] | None = None,
    ):
        self._devive_args: dict[str, str | None] = {
            'name': name, 'phys': phys, 'uniq': uniq}
        self.device: InputDevice = find_device(**self._devive_args)
        self.stroke: _Stroke = _Stroke()
        self._remap: dict[int, int] | None = remap
        self._no_pass_through: set[int] | None = no_pass_throuth
        self.press_history: dict[int, float] = {}
        self.data: dict[Any, Any] = {}  # pyright: ignore[reportExplicitAny]
        self._shortcut_registry: dict[int, list[_BoundShortcut]] = {}

    def _register_shortcuts(self):
        for shortcuts in self._shortcut_registry.values():
            shortcuts.sort(key=lambda s: s.priority, reverse=True)

    def _prepare(self):
        # Wait until device is idle.
        while self.device.active_keys():
            sleep(0.05)

        # Refresh history (if after a reconnection.)
        self.press_history.clear()
        self.data.clear()

    def _event_loop(self) -> Never:  # pyright: ignore[reportReturnType]
        with self.device.grab_context():
            for event in cast(SupportsReadLoop, self.device).read_loop():
                e = categorize(event)
                if not isinstance(e, KeyEvent):
                    continue
                assert isinstance(e, KeyEvent)
                if self._remap is not None:
                    e.scancode = self._remap.get(e.scancode, e.scancode)

                if e.keystate == KeyEvent.key_down:
                    self.press_history[e.scancode] = e.event.timestamp()

                shortcut_result: ShortcutResult = 'reject'
                shortcuts = self._shortcut_registry.get(e.scancode)
                if shortcuts is not None:
                    for shortcut in shortcuts:
                        shortcut_result = shortcut(e)
                        if shortcut_result != 'reject':
                            break
                if (shortcut_result == 'reject' and (
                    self._no_pass_through is None or
                        e.scancode not in self._no_pass_through)):
                    self.stroke.write_raw(e.scancode, e.keystate)

                if e.keystate == KeyEvent.key_up:
                    del self.press_history[e.scancode]

    def _reset_device(self):
        while True:
            sleep(2)
            try:
                self.device = find_device(**self._devive_args)
                break
            except ValueError:
                pass

    def serve(self):
        self._register_shortcuts()

        while True:
            try:
                self._prepare()
                self._event_loop()
            except OSError as e:
                # /usr/include/asm-generic/errno-base.h
                # ENODEV = 19, 'No such device'
                if e.args[0] == 19:
                    self._reset_device()
                else:
                    raise

    def __call__(
        self,
        key_code: int,
        *,
        on: On = 'raw',
        for_duration: float = 0.3,
        with_modifiers: Sequence[int] = (),
        before: Before | None = None,
        after: After | None = None,
    ) -> Callable[[Shortcut], _BoundShortcut]:
        def decorator(shortcut: Shortcut) -> _BoundShortcut:
            bound_shortcut = _BoundShortcut(
                shortcut,
                on=on,
                duration=for_duration,
                modifiers=with_modifiers,
                before=before,
                after=after,
                bind=self
            )

            if key_code not in self._shortcut_registry:
                self._shortcut_registry[key_code] = []
            self._shortcut_registry[key_code].append(bound_shortcut)

            return bound_shortcut
        return decorator

    def no_op(
        self,
        key_code: int,
        *,
        before: Before | None = None,
        after: After | None = None
    ):
        _ = self.__call__(key_code, on='no_op',
                          before=before, after=after)(lambda _: None)

    def partial(
        self,
        *,
        on: On = 'raw',
        for_duration: float = 0.3,
        with_modifiers: Sequence[int] = (),
        prepend_before: Before | None = None,
        append_before: Before | None = None,
        prepend_after: After | None = None,
        append_after: After | None = None,
    ):
        class _PartialBind():
            def __init__(
                self,
                bind: Bind,
                prepend_before: Before | None = None,
                append_before: Before | None = None,
                prepend_after: After | None = None,
                append_after: After | None = None,
            ) -> None:
                self.bind: Bind = bind
                self.prepend_before: Before | None = prepend_before
                self.append_before: Before | None = append_before
                self.prepend_after: After | None = prepend_after
                self.append_after: After | None = append_after

            def __call__(
                self,
                key_code: int,
                on: On = on,
                for_duration: float = for_duration,
                with_modifiers: Sequence[int] = with_modifiers,
                before: Before | None = None,
                after: After | None = None,
            ):
                complete_before: Before = []
                if prepend_before is not None:
                    complete_before.extend(prepend_before)
                if before is not None:
                    complete_before.extend(before)
                if append_before is not None:
                    complete_before.extend(append_before)

                complete_after: After = []
                if prepend_after is not None:
                    complete_after.extend(prepend_after)
                if after is not None:
                    complete_after.extend(after)
                if append_after is not None:
                    complete_after.extend(append_after)

                return self.bind.__call__(
                    key_code,
                    on=on,
                    for_duration=for_duration,
                    with_modifiers=with_modifiers,
                    before=complete_before if complete_before else None,
                    after=complete_after if complete_after else None
                )

            def no_op(
                self,
                key_code: int,
                *,
                before: Before | None = None,
                after: After | None = None,
            ):
                _ = self.__call__(key_code, on='no_op',
                                  before=before, after=after)(lambda _: None)
        return _PartialBind(self, prepend_before, append_before,
                            prepend_after, append_after)
