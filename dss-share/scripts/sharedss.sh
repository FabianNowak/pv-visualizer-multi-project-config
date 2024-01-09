#!/bin/bash

# Set to the path where the dss container is mounted (e.g. /dss/<containername>)
dss_mountpath=

if [ -z "$dss_mountpath" ]
then
  echo "sharedss not fully configured"
  exit 2
fi

case $1 in
  share)
    sudo /opt/sharedss/mount-for-all.sh "$dss_mountpath" "$2"
    ;;

  unshare)
    sudo /opt/sharedss/unmount.sh
    ;;

  allow)
    sudo /opt/sharedss/allow-access.sh "$2"
    ;;

  revoke)
    sudo /opt/sharedss/revoke-access.sh "$2"
    ;;

  list)
    sudo /opt/sharedss/list-group.sh
    ;;
  *)
    echo "Usage:"
    echo "sharedss share <subfolder>  (Share a subfolder relative to your DSS user directory)"
    echo "sharedss unshare (Stop sharing the previously shared subfolder; also revokes all access rights)"
    echo "sharedss allow <username> (Grant the user <username> access to the shared directory)"
    echo "sharedss revoke <username> (Revoke previously granted access for <username>)"
    echo "sharedss list (List all users with access)"
    ;;
esac