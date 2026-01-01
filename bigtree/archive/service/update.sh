#!/bin/bash
WORKDIR=~/.config/bigtree
cd $WORKDIR
git fetch
update_status=$(git log ..origin/main --oneline | wc -l)
if (( update_status > 0 )); then
    echo -e "Stopping BigTree"
    systemctl stop bigtree --user
    git pull
    /bin/cp -rf ~/.config/bigtree/service/bigtree.service ~/.config/systemd/user/bigtree.service
    /bin/cp -rf ~/.config/bigtree/service/bigtreeupdate.service ~/.config/systemd/user/bigtreeupdate.service
    /bin/cp -rf ~/.config/bigtree/service/bigtreeupdate.timer ~/.config/systemd/user/bigtreeupdate.timer
    systemctl daemon-reload --user
    echo -e "Starting BigTree"
    systemctl start bigtree --user
fi
