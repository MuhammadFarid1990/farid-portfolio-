#!/usr/bin/env bash
# Wrapper that loops the agent so the "Pull & Restart" button can
# exit with code 42 and we just start it back up.
set +e
while true; do
  echo
  echo "=== Starting job agent (Ctrl+C to stop) ==="
  echo
  python agent.py
  code=$?
  if [ "$code" != "42" ]; then
    echo
    echo "=== Agent exited with code $code. Done. ==="
    exit $code
  fi
  echo
  echo "=== Restart requested by dashboard, relaunching... ==="
  echo
  sleep 2
done
