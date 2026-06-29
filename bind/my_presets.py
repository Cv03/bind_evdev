# pyright: reportUnusedCallResult=false, reportArgumentType=false, reportUnusedFunction=false

import subprocess

from time import sleep
from evdev import ecodes, InputEvent, KeyEvent

from .bind_evdev import Bind


def numpad_shortcuts(bind: Bind):
    k = ecodes

    numpad_key_codes = frozenset((
        ecodes.KEY_KP0,
        ecodes.KEY_KP1,
        ecodes.KEY_KP2,
        ecodes.KEY_KP3,
        ecodes.KEY_KP4,
        ecodes.KEY_KP5,
        ecodes.KEY_KP6,
        ecodes.KEY_KP7,
        ecodes.KEY_KP8,
        ecodes.KEY_KP9,
        ecodes.KEY_KPDOT,
        ecodes.KEY_KPENTER,
        ecodes.KEY_KPPLUS,
        ecodes.KEY_KPMINUS,
        ecodes.KEY_KPASTERISK,
        ecodes.KEY_KPSLASH,
    ))

    def raw_numpad_keys_when_numlock_on(bind: Bind, e: InputEvent):
        if (e.code in numpad_key_codes and
                ecodes.LED_NUML in bind.device.leds()):
            return True

    assert bind.global_before is not None
    bind.global_before.append(raw_numpad_keys_when_numlock_on)

    def capture_unmapped_numpad_keys(bind: Bind, e: InputEvent):
        if (e.code in numpad_key_codes and
                ecodes.LED_NUML not in bind.device.leds()):
            return False

    assert bind.global_after is not None
    bind.global_after.append(capture_unmapped_numpad_keys)

    bind(k.KEY_BRIGHTNESSUP, to_key=[k.KEY_KPPLUS, k.KEY_KPSLASH], on='tap')

    bind([k.KEY_LEFTCTRL, k.KEY_Z], to_key=k.KEY_KPSLASH, on='tap_release')
    bind([k.KEY_LEFTCTRL, k.KEY_X], to_key=k.KEY_KPSLASH, on='hold')

    bind([k.KEY_LEFTCTRL, k.KEY_Y], to_key=k.KEY_KPASTERISK, on='tap_release')
    bind([k.KEY_LEFTCTRL, k.KEY_C], to_key=k.KEY_KPASTERISK, on='hold')

    bind([k.KEY_LEFTCTRL, k.KEY_A], to_key=k.KEY_KPMINUS, on='tap_release')
    bind([k.KEY_LEFTCTRL, k.KEY_V], to_key=k.KEY_KPMINUS, on='hold')

    bind(k.KEY_VOLUMEDOWN, to_key=[k.KEY_KPPLUS, k.KEY_KP7])
    bind(k.KEY_HOME, to_key=k.KEY_KP7)
    bind(k.KEY_PAGEUP, to_key=[k.KEY_KP8, k.KEY_KP7])

    bind(k.KEY_BRIGHTNESSDOWN, to_key=[k.KEY_KPPLUS, k.KEY_KP8], on='tap')

    bind(k.KEY_VOLUMEUP, to_key=[k.KEY_KPPLUS, k.KEY_KP9])
    bind(k.KEY_END, to_key=k.KEY_KP9)
    bind(k.KEY_PAGEDOWN, to_key=[k.KEY_KP8, k.KEY_KP9])

    def set_kpenter_mode(to: str, bind: Bind, _e: InputEvent):
        if k.KEY_KPENTER not in bind.pressed:
            return False

        mode: str | None = bind.data.get('kpenter_mode')
        if mode is None:
            bind.data['kpenter_mode'] = to
            if to == 'alt_tab':
                bind.uinput.raw(k.KEY_LEFTALT, KeyEvent.key_down)
        elif mode != to:
            return False

    bind([k.KEY_LEFTSHIFT, k.KEY_TAB], to_key=k.KEY_KP4,
         on='tap', before=[lambda b, e: set_kpenter_mode('alt_tab', b, e)])
    bind(k.KEY_TAB, to_key=k.KEY_KP5,
         on='tap', before=[lambda b, e: set_kpenter_mode('alt_tab', b, e)])

    # Minimize window
    bind([k.KEY_LEFTMETA, k.KEY_PAGEDOWN], to_key=[k.KEY_KPENTER, k.KEY_KP1],
         on='tap', before=[lambda b, e: set_kpenter_mode('window', b, e)])
    bind(k.KEY_ESC, to_key=k.KEY_KP1)
    # Maximize window
    bind([k.KEY_LEFTMETA, k.KEY_PAGEUP], to_key=[k.KEY_KPENTER, k.KEY_KP2],
         on='tap', before=[lambda b, e: set_kpenter_mode('window', b, e)])
    # Zoom out
    bind([k.KEY_LEFTMETA, k.KEY_MINUS], to_key=k.KEY_KP2, on='tap')
    # Close window
    bind([k.KEY_LEFTALT, k.KEY_F4], to_key=[k.KEY_KPENTER, k.KEY_KP3],
         on='tap', before=[lambda b, e: set_kpenter_mode('window', b, e)])
    # Zoom in
    bind([k.KEY_LEFTMETA, k.KEY_EQUAL], to_key=k.KEY_KP3, on='tap')

    @bind(to_key=k.KEY_KPENTER)
    def unset_kpenter_mode(bind: Bind, e: InputEvent):
        if e.value != KeyEvent.key_up:
            return
        mode: str | None = bind.data.get('kpenter_mode')
        if mode == 'alt_tab':
            bind.uinput.raw(k.KEY_LEFTALT, KeyEvent.key_up)
        bind.data['kpenter_mode'] = None

    @bind(to_key=k.KEY_KP0, on='tap')
    def command_goldendict_popup(bind: Bind, _e: InputEvent):
        ps_result = subprocess.run(['flatpak', 'ps', '--columns=application'],
                                   capture_output=True, text=True)
        running_app_ids = [
            line.strip() for line in ps_result.stdout.splitlines()]
        if not 'io.github.xiaoyifang.goldendict_ng' in running_app_ids:
            return

        bind.uinput.hotkey(ecodes.KEY_LEFTCTRL, ecodes.KEY_C)
        sleep(0.03)
        run_result = subprocess.run(['wl-paste', '-n', '-t', 'text'],
                                    capture_output=True, text=True)
        if run_result.returncode == 0 and run_result.stdout:
            _ = subprocess.run(
                ['flatpak', 'run', '--branch=stable', '--arch=x86_64',
                 '--command=goldendict', '--file-forwarding',
                 'io.github.xiaoyifang.goldendict_ng',
                 '--popup', run_result.stdout])

    bind([k.KEY_LEFTMETA, k.KEY_V], to_key=k.KEY_KPDOT, on='tap')


def dbus_monitor_watchdog(name: str | None = None, uniq: str | None = None):
    command = ['./bt_conn_mon.sh']
    if name is not None:
        command.append(f'--name={name}')
    if uniq is not None:
        command.append(f'--address={uniq}')
    _ = subprocess.run(command, check=True)


def system_bus_watchdog(name: str | None = None, uniq: str | None = None):
    command = ['python', 'system_bus_watchdog.py']
    if name is not None:
        command.append(f'--name={name}')
    if uniq is not None:
        command.append(f'--address={uniq}')
    _ = subprocess.run(command, check=True)
