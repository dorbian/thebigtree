#!/bin/bash
WORKDIR=~/.config/bigtree
DATADIR=/data/thebigtree
cd $WORKDIR
update_status=${git remote update ; git status -uno}
echo $update_status