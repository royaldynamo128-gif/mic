#!/bin/bash
export PATH="/home/rai/.postgres_local/usr/lib/postgresql/18/bin:$PATH"
export LD_LIBRARY_PATH="/home/rai/.postgres_local/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH"

case "$1" in
  start)
    pg_ctl -D /home/rai/.postgres_data -l /home/rai/.postgres_data/logfile start
    ;;
  stop)
    pg_ctl -D /home/rai/.postgres_data stop
    ;;
  status)
    pg_ctl -D /home/rai/.postgres_data status
    ;;
  *)
    echo "Usage: $0 {start|stop|status}"
    exit 1
    ;;
esac
