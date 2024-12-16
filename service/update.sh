#!/bin/bash
WORKDIR=~/.config/bigtree
cd $WORKDIR
update_status=$(git log ..origin/main --oneline | wc -l)
if (( update_status > 0 )); then
    systemctl stop bigtree --user
    git pull    
    cp ~/.config/bigtree/service/bigtree.service ~/.config/systemd/user/bigtree.service
    systemctl daemon-reload --user
    systemctl start bigtree --user
fi