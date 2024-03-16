#!/bin/bash

source $(dirname "$0")/definitions.sh

for FILE in "$sharedss_var_lib_mounts"/*; do
  echo "Starting $FILE"
  if [ -f "$FILE" ]; then
    username="$(basename "$FILE")"
    groupname=$(dss_access_group_of "$username")
    dir=$(sharedss_dir "$username")
    read -r dssdir<"$sharedss_var_lib_mounts/$username"
    sudo -u "$username" bindfs -g "$groupname" -p u=rx,g=rx,o= --realistic-permissions "$dssdir" "$dir"
  fi
done
