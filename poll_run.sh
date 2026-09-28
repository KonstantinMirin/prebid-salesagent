#!/bin/bash
# Poll the cassini run until it leaves the running state, printing progress each minute
# so no watchdog sees a silent wait. Deleted before commit.
export REMOTE_TEST_HOST=noetis-b-vm
RUN_ID="$1"
for i in $(seq 1 90); do
  line=$(cassini status "$RUN_ID" 2>&1 | sed 's/\x1b\[[0-9;]*m//g' | grep -E "state|doing|suite|MISSING" | tr '\n' ' ')
  echo "poll $i: $line"
  if ! echo "$line" | grep -q "state  : running"; then
    echo "TERMINAL"
    exit 0
  fi
  sleep 60
done
echo "POLL LIMIT REACHED"
