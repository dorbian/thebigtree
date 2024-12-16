#!/bin/sh

# check if user systemd dir exists
if [ ! -d "~/.config/systemd/user" ]; then
    mkdir -p ~/.config/systemd/user
fi

if [ ! -d "~/.config/bigtree" ]; then
    mkdir -p ~/.config/bigtree
    # Download latest to destination
    git clone https://github.com/dorbian/thebigtree.git ~/.config/bigtree
fi
# Check if update service exists
if [ ! -e ~/.config/systemd/user/bigtreeupdate.service ]; then
    cp ~/.config/bigtree/service/bigtreeupdate.service ~/.config/systemd/user/bigtreeupdate.service
    cp ~/.config/bigtree/service/bigtreeupdate.timer ~/.config/systemd/user/bigtreeupdate.timer
    systemctl daemon-reload --user
    systemctl enable bigtreeupdate.timer --user
fi
# Checking if service exists
if [ ! -e ~/.config/systemd/user/bigtree.service ]; then
    cp ~/.config/bigtree/service/bigtree.service ~/.config/systemd/user/bigtree.service
    systemctl daemon-reload --user
    systemctl enable bigtree.service --user
    systemctl start bigtree.service --user
fi
  systemctl restart bigtreeupdate.timer --user