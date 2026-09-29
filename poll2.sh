#!/bin/bash
# Poll the final cassini run until it leaves the running state, printing each minute so no
# watchdog sees a silent wait. Removed before the final commit.
export REMOTE_TEST_HOST=noetis-b-vm
for i in $(seq 1 90); do
  line=$(cassini status sa-cf74c8d3 2>&1 | sed 's/\x1b\[[0-9;]*m//g' | grep -E "state|doing" | tr '\n' ' ')
  echo "poll $i: $line"
  if ! echo "$line" | grep -q "state  : running"; then
    echo "TERMINAL"
    exit 0
  fi
  sleep 60
done
echo "POLL LIMIT"
