#!/bin/bash

NTPCONF="/etc/ntp.conf"
GPSDDEFAULT="/etc/default/gpsd"

if ! grep -q "127.127.28.0" "$NTPCONF"; then
    echo '
# GPS Serial data reference
server 127.127.28.0 minpoll 4 maxpoll 4
fudge 127.127.28.0 time1 0.0 refid GPS

# GPS PPS reference
server 127.127.28.1 minpoll 4 maxpoll 4 prefer
fudge 127.127.28.1 refid PPS

' >> "$NTPCONF"
fi

if grep -q '^GPSD_OPTIONS=' "$GPSDDEFAULT"; then
    sed -i 's/^GPSD_OPTIONS=".*"$/GPSD_OPTIONS="-n"/' "$GPSDDEFAULT"
else
    echo 'GPSD_OPTIONS="-n"' >> "$GPSDDEFAULT"
fi

if command -v systemctl >/dev/null 2>&1; then
    echo "Detected systemd"
    systemctl restart ntpd
elif command -v sv >/dev/null 2>&1; then
    echo "Detected runit"
    sv restart ntpd
elif command -v service >/dev/null 2>&1; then
    echo "Detected sysvinit"
    service ntpd restart
else
    echo "Unsupported init system"
    exit 1
fi

exit 0