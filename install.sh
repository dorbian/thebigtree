#!/bin/bash

# check if user systemd dir exists

if [ ! -f ~/.config/systemd/user/bigtreeupdate.service ]; then
    echo -e "Creating systemd user directory"
    mkdir -p ~/.config/systemd/user
fi
if [ ! -f ~/.config/bigtree/thebigtree.py ]; then
    echo -e "Creating bigtree directory"
    mkdir -p ~/.config/bigtree
    # Download latest to destination
    git clone https://github.com/dorbian/thebigtree.git ~/.config/bigtree
fi
# Check if update service exists
if [ ! -f ~/.config/systemd/user/bigtreeupdate.service ]; then
    echo -e "Creating Update Service"
    cp ~/.config/bigtree/service/bigtreeupdate.service ~/.config/systemd/user/bigtreeupdate.service
    cp ~/.config/bigtree/service/bigtreeupdate.timer ~/.config/systemd/user/bigtreeupdate.timer
    systemctl daemon-reload --user
    systemctl enable bigtreeupdate.timer --user
fi
# Checking if service exists
if [ ! -f ~/.config/systemd/user/bigtree.service ]; then
    echo -e "Creating service for BigTree Discord Bot"
    cp ~/.config/bigtree/service/bigtree.service ~/.config/systemd/user/bigtree.service
    systemctl daemon-reload --user
    systemctl enable bigtree.service --user
    systemctl start bigtree.service --user
fi
echo -e "Starting update service"
systemctl restart bigtreeupdate.timer --user