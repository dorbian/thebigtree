#!/bin/bash
WORKDIR=~/.config/bigtree
DATADIR=/data/thebigtree
cd $WORKDIR
git remote update
update_status=${git status -uno}
echo $update_status