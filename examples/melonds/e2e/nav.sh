#!/usr/bin/env bash
# nav.sh <sdir> <sav> <port>: load SLOT 1, open Unit Info > Luso > Set Abilities > Chivalry picker
S=$1; M=/tmp/opencode/mds.sh
/tmp/opencode/flow.sh "$S" "$2" "$3" boot load:1 >/dev/null 2>&1
n=0; st(){ for t in "$@"; do $M seq "$S" "$t"; done; n=$((n+1)); $M shot "$S" "n$(printf %02d $n)" >/dev/null; }
st x:0.2:2.5; st a:0.2:3; st a:0.2:3; st down:0.2:1.5; st a:0.2:3; st down:0.2:1.5; st a:0.2:3
st down:0.2:1.5; st down:0.2:1.5; st up:0.2:1.5; st b:0.2:2; st b:0.2:2; st b:0.2:2
