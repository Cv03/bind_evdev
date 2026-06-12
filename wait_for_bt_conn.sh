#!/bin/bash

while [[ -n $1 ]]; do
    case "$1" in
        --name=* )
            name="${1#--name=}"
            name_pattern="s +\"$name\""
            ;;
        --address=* )
            address="${1#--address=}"
            address=${address^^}
            address_pattern="s +\"$address\""
            ;;
        * )
            break
            ;;
    esac
    shift
done

if [[ -z $name && -z $address ]]; then
    echo 'Supported criteria: name, address. Specify one at least.' >&2
    exit 1
fi

# Suppress stderr to remove the `dbus-monitor` warning "Falling back to
# eavesdropping."
# `busctl monitor` has yet to support the eavesdropping fallback behavior.
# See: https://github.com/systemd/systemd/issues/26310#issuecomment-1685170189
dbus-monitor --system "type='signal',sender='org.bluez',interface='org.freedesktop.DBus.Properties',member='PropertiesChanged'" 2> /dev/null | \
while read -r line; do
    if [[ "$line" =~ path=([^;]+) ]]; then
        device_path="${BASH_REMATCH[1]}"
    fi

    if [[ "$line" == *"string \"Connected\""* ]]; then
        read -r val_line
        if [[ "$val_line" == *"boolean true"* ]]; then
            if [[ -n $name ]]; then
                device_name="$(busctl --system get-property org.bluez "$device_path" org.bluez.Device1 Name)"
                if [[ ! $device_name =~ $name_pattern ]]; then
                    continue
                fi
            fi
            if [[ -n $address ]]; then
                device_address="$(busctl --system get-property org.bluez "$device_path" org.bluez.Device1 Address)"
                if [[ ! $device_address =~ $address_pattern ]]; then
                    continue
                fi
            fi
            exit
        fi
    fi
done
