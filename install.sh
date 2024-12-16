#!/bin/sh
curdir=${pwd}
# allow user mode systemd over ssh
loginctl --enable-linger
# check if user systemd dir exists
if [ ! -d "~/.config/systemd/user" ]; then
    mkdir -p ~/.config/systemd/user
fi

if [ ! -d "~/.config/bigtree" ]; then
    mkdir -p ~/.config/bigtree
fi
# Download latest to destination
git clone https://github.com/dorbian/thebigtree.git ~/.config/bigtree
# Checking if service exists
if [ ! -e ~/.config/systemd/user/bigtree.service ]; then
    cp ~/.config/bigtree/service/bigtree.service ~/.config/systemd/user/bigtree.service
    systemctl daemon-reload --user
    systemctl enable bigtree.service --user
    systemctl start bigtree.service --user
fi
# Copy cronjob if needed
# cp checkscript
# chmod checkscript chmod 755 hourly-event.sh