from typing import Protocol, cast, Any, Never, Callable, Literal
from sys import stderr
from collections import defaultdict
from collections.abc import Sequence, Iterator, Mapping
from time import sleep

from evdev import KeyEvent, ecodes, InputEvent, UInput, InputDevice
from evdev import list_devices  # pyright:ignore[reportUnknownVariableType]


class _SupportWriteAndSyn(Protocol):
    def write(self, etype: int, code: int, value: int) -> None: ...
    def syn(self) -> None: ...


class _SupportsReadLoop(Protocol):
    def read_loop(self) -> Iterator[InputEvent]: ...


type On = Literal['raw', 'tap', 'tap_release', 'hold', 'hold_release', 'never']
type Before = Callable[[Bind, InputEvent], bool | None]
type ShortcutFn = Callable[[Bind, InputEvent], bool | None]
type After = Callable[[Bind, InputEvent], bool | None]


class _UInput:
    __slots__: tuple[str, ...] = ('_uinput',)

    def __init__(self):
        events = {ecodes.EV_KEY: tuple(code for code in ecodes.keys.keys() if (
            code < 288 or 318 < code < 544 or 547 < code < 704 or 743 < code))}
        # Excluded joystick buttons [288, 318] ∪ [544, 547] ∪ [704, 743],
        # necessary for mouse buttons support.
        self._uinput: _SupportWriteAndSyn = cast(
            _SupportWriteAndSyn, UInput(
                events=events, name='bind-evdev_virtual_device'))  # pyright:ignore[reportArgumentType]

    def raw(self, key_code: int, event_value: int):
        self._uinput.write(ecodes.EV_KEY, key_code, event_value)
        self._uinput.syn()

    def type_(self, key_code: int):
        self.raw(key_code, KeyEvent.key_down)
        sleep(0.005)
        self.raw(key_code, KeyEvent.key_up)

    def hotkey(self, *key_codes: int):
        for key_code in key_codes:
            self.raw(key_code, KeyEvent.key_down)
            sleep(0.005)
        for key_code in key_codes[::-1]:
            self.raw(key_code, KeyEvent.key_up)
            sleep(0.005)


class _Shortcut:
    __slots__: tuple[str, ...] = ('bind', 'for_duration', 'before', 'shortcut_fn', 'after')

    def __init__(
        self,
        bind: Bind,
        shortcut_fn: ShortcutFn,
        for_duration: float = 0.3,
        before: Sequence[Before] | None = None,
        after: Sequence[After] | None = None
    ):
        self.bind: Bind = bind
        self.for_duration: float = for_duration
        self.before: Sequence[Before] | None = before
        self.shortcut_fn: ShortcutFn = shortcut_fn
        self.after: Sequence[After] | None = after

    def __call__(self, event: InputEvent):
        if self.before:
            before_flag = None
            for b in self.before:
                if (flag := b(self.bind, event)) is not None:
                    before_flag = before_flag or flag
            if before_flag is not None:
                return before_flag

        shourtcut_fn_flag = self.shortcut_fn(self.bind, event)

        if self.after:
            after_flag = None
            for a in self.after:
                if (flag := a(self.bind, event)) is not None:
                    after_flag = after_flag or flag
            if after_flag is not None:
                return after_flag

        return shourtcut_fn_flag


class _NoOpShortcut(_Shortcut):
    def __init__(
        self,
        bind: Bind,
        before: Sequence[Before] | None = None,
    ):
        super().__init__(bind, lambda _b, _e: None, 0.3, before)


def find_device(
    *,
    name: str | None = None,
    phys: str | None = None,
    uniq: str | None = None
):
    print_to_stdout = name is None and phys is None and uniq is None
    found_devices: list[InputDevice[str]] = []
    for path in list_devices():
        device = InputDevice[str](path)
        if print_to_stdout:
            print(f"name='{device.name}', phys='{(
                device.phys)}', uniq='{device.uniq}'")
        else:
            if (name is None or name == device.name) and (
                    phys is None or phys == device.phys) and (
                        uniq is None or uniq == device.uniq):
                found_devices.append(device)
    if not print_to_stdout:
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
                    print(f"name='{device.name}', phys='{(
                        device.phys)}', uniq='{device.uniq}'", file=stderr)
                raise ValueError('More than one device found.')


def _split_key(key: int | Sequence[int]):
    if isinstance(key, int):
        trigger = key
        modifier = frozenset[int]()
    else:
        if not key:
            raise ValueError('Empty key sequence.')
        trigger = key[-1]
        modifier = frozenset(key[:-1])
    return (trigger, modifier)


class Bind:
    def __init__(
        self,
        *,
        name: str | None = None,
        phys: str | None = None,
        uniq: str | None = None,
        remap: Mapping[int, int] | None = None,
        global_before: Sequence[Before] | None = None,
        global_after: Sequence[After] | None = None,
    ):
        self.device: InputDevice[str] = cast(InputDevice[
            str], find_device(name=name, phys=phys, uniq=uniq))

        # Wait until device idle.
        while self.device.active_keys():
            sleep(0.1)
        self.device.grab()

        self.uinput: _UInput = _UInput()

        self._remap: dict[int, int] = dict(remap) if remap else {}
        self._registry: defaultdict[
            int, defaultdict[frozenset[int], defaultdict[On, _Shortcut | None]]] = defaultdict(lambda: defaultdict(defaultdict))

        self.pressed: set[int] = set()
        self.trigger_timestamp: dict[int, float] = {}
        # Fronzen at serving.
        self._keep_timestamp: set[int] | frozenset[int] = set()
        self.data: dict[Any, Any] = {  # pyright: ignore[reportExplicitAny]
            '_hold_fired': set[int](),
            '_catch_raw_modifiers': dict[int, frozenset[int]](),
        }

        self.global_before: list[Before] | None = []
        if global_before:
            self.global_before.extend(global_before)
        self.global_after: list[After] | None = []
        if global_after:
            self.global_after.extend(global_after)

    def _sort_shortcuts_by_modifier_number(self):
        for v in self._registry.values():
            l = [(kk, vv) for kk, vv in v.items()]
            l.sort(key=lambda x: len(x[0]), reverse=True)
            v.clear()
            for kk, vv in l:
                v[kk] = vv

    def _clean_states(self):
        self.pressed.clear()
        self.trigger_timestamp.clear()

        cast(set[int], self.data['_hold_fired']).clear()
        cast(dict[int, frozenset[int]], self.data['_catch_raw_modifiers']).clear()
        kept_data_keys = ('_hold_fired', '_catch_raw_modifiers')
        data_keys_to_remove = (k for k in self.data if k not in kept_data_keys)  # pyright: ignore[reportAny]
        for k in data_keys_to_remove:  # pyright: ignore[reportAny]
            del self.data[k]

    def serve(self) -> Never:  # pyright: ignore[reportReturnType]
        self._sort_shortcuts_by_modifier_number()
        self._keep_timestamp = frozenset(self._keep_timestamp)

        self._clean_states()

        if not self.global_before:
            self.global_before = None
        if not self.global_after:
            self.global_after = None

        try:
            for e in cast(_SupportsReadLoop, self.device).read_loop():
                if e.type != ecodes.EV_KEY:
                    continue

                if e.code in self._remap:
                    e.code = self._remap[e.code]

                if e.value == KeyEvent.key_down:
                    self.pressed.add(e.code)
                    if e.code in self._keep_timestamp:
                        self.trigger_timestamp[e.code] = e.timestamp()

                is_fire_original = e.code not in self._registry

                global_before_flag = None
                if self.global_before:
                    for gb in self.global_before:
                        if (flag := gb(self, e)) is not None:
                            global_before_flag = global_before_flag or flag
                    if global_before_flag is not None:
                        is_fire_original = global_before_flag

                if not is_fire_original and global_before_flag is None:
                    for modifier, shortcuts in self._registry[e.code].items():
                        if modifier.issubset(self.pressed):
                            if 'never' in shortcuts:
                                break

                            if s := shortcuts.get('raw'):
                                is_fire_original = s(e)
                                self.data['_catch_raw_modifiers'][e.code] = modifier

                            match e.value:
                                case KeyEvent.key_down:
                                    if s := shortcuts.get('tap'):
                                        is_fire_original = s(e)
                                case KeyEvent.key_hold:
                                    if (s := shortcuts.get('hold')) and e.code not in self.data['_hold_fired']:
                                        if e.timestamp() - self.trigger_timestamp[e.code] > s.for_duration:
                                            is_fire_original = s(e)
                                            if not is_fire_original:
                                                cast(set[int], self.data['_hold_fired']).add(e.code)
                                case KeyEvent.key_up:
                                    if s := shortcuts.get('tap_release'):
                                        # Assume no tap is longer than 0.3 seconds.
                                        if e.timestamp() - self.trigger_timestamp[e.code] < 0.3:
                                            is_fire_original = s(e)
                                    elif s := shortcuts.get('hold_release'):
                                        if e.timestamp() - self.trigger_timestamp[e.code] > s.for_duration:
                                            is_fire_original = s(e)

                                    if 'hold' in shortcuts and e.code in self.data['_hold_fired']:
                                        cast(set[int], self.data['_hold_fired']).remove(e.code)
                                case _:
                                    raise ValueError('_not_possible_')

                            break

                global_after_flag = None
                if self.global_after:
                    for ga in self.global_after:
                        if (flag := ga(self, e)) is not None:
                            global_after_flag = global_after_flag or flag
                    if global_after_flag is not None:
                        is_fire_original = global_after_flag

                if is_fire_original:
                    self.uinput.raw(e.code, e.value)

                if e.value == KeyEvent.key_up:
                    if e.code in self.pressed:
                        self.pressed.remove(e.code)
                    if e.code in self.trigger_timestamp:
                        del self.trigger_timestamp[e.code]
        except OSError as e:
            # /usr/include/asm-generic/errno-base.h
            # #define ENODEV 19 /* No such device */
            if e.args[0] == 19:
                exit()
            else:
                raise
        except KeyboardInterrupt:
            exit()

    def __call__(
        self,
        *args: int | Sequence[int] | ShortcutFn | None,
        to_key: int | Sequence[int],
        on: On = 'raw',
        for_duration: float = 0.3,
        before: Sequence[Before] | None = None,
        after: Sequence[After] | None = None,
    ):
        match len(args):
            case 1:
                return self.inline(args[0], to_key=to_key, on=on, for_duration=for_duration, before=before, after=after)
            case 0:
                return self.decorator(to_key=to_key, on=on, for_duration=for_duration, before=before, after=after)
            case _:
                raise TypeError('Too many positional arguments.')

    def inline(
        self,
        operation: int | Sequence[int] | ShortcutFn | None,
        /,
        *,
        to_key: int | Sequence[int],
        on: On = 'raw',
        for_duration: float = 0.3,
        before: Sequence[Before] | None = None,
        after: Sequence[After] | None = None,
    ):
        trigger, modifier = _split_key(to_key)

        if operation is None:
            self._registry[trigger][modifier]['raw'] = _NoOpShortcut(
                self, before)
            return

        if on == 'raw':
            if isinstance(operation, int):
                def _r(bind: Bind, e: InputEvent):
                    bind.uinput.raw(operation, e.value)
                shortcut_fn = _r
            else:
                raise TypeError('RAW shortcuts accept only int operations.')
        else:
            if isinstance(operation, int):
                def _i(bind: Bind, _e: InputEvent):
                    bind.uinput.type_(operation)
                shortcut_fn = _i
            elif isinstance(operation, Sequence):
                def _si(bind: Bind, _e: InputEvent):
                    bind.uinput.hotkey(*operation)
                shortcut_fn = _si
            else:
                shortcut_fn = operation
        shortcut = _Shortcut(self, shortcut_fn, for_duration, before, after)
        cast(set[int], self._keep_timestamp).add(trigger)
        self._registry[trigger][modifier][on] = shortcut

    def decorator(
        self,
        *,
        to_key: int | Sequence[int],
        on: On = 'raw',
        for_duration: float = 0.3,
        before: Sequence[Before] | None = None,
        after: Sequence[After] | None = None,
    ):
        def decorator(shortcut_fn: ShortcutFn):
            trigger, modifier = _split_key(to_key)
            shortcut = _Shortcut(self, shortcut_fn, for_duration, before, after)
            cast(set[int], self._keep_timestamp).add(trigger)
            self._registry[trigger][modifier][on] = shortcut
            return shortcut
        return decorator


if __name__ == '__main__':
    _ = find_device()
