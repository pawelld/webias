#!/bin/bash
# chkconfig: 345 95 05

. /etc/init.d/functions

PIDFILE=/tmp/WeBIAS.pid
WEBIAS=/var/www/WeBIAS/WeBIAS.py

# Start the service WeBIAS
start() {
        if [ -f $PIDFILE ]; then
            echo "There is another instance of WeBIAS running with PID:" $(cat $PIDFILE)
        else
            echo "Starting WeBIAS server"
			$WEBIAS 
			sleep 3
        fi        
}

# Restart the service WeBIAS
stop() {
        if [ -f $PIDFILE ]; then
            echo "Stopping WeBIAS server"
            kill -15 $(cat $PIDFILE)
        else
            echo "WeBIAS was not running"
        fi
}
# Check status of the service WeBIAS
status() {
        if [ -f  $PIDFILE ]; then
            echo "WeBIAS is running with PID:" $(cat $PIDFILE)
        else
            echo "WeBIAS is not running"
        fi
}

### main logic ###
case "$1" in
  'start')
        start
        ;;
  'stop')
        stop
        ;;
  'status')
        status
        ;;
  'restart')
        stop
        sleep 5
        start
        ;;
  *)
        echo $"Usage: $0 {start|stop|restart|status}"
        exit 1
esac

exit 0
