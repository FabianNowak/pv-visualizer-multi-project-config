#!/bin/bash

# use as mount-for-all /dss/<containername> <subdirofuser>
# e.g. mount-for-all "/dss/t1234/" "share/" to share the "/dss/t1234/<username>/share" directory of the calling user


source $(dirname "$0")/definitions.sh

check_error() {
  local code=$?
  echo "Error: Line $1"
  exit $code
}

check_error_and_cleanup() {
  local code=$?
  if [[ $code -ne 0 ]]
  then
    rm -d "$dir" 2>/dev/null
    rm "$sharedss_var_lib_mounts/$access_to_user" 2>/dev/null
    echo "Error: Line $1"
    exit $code
  fi
}

wait_input() {
  echo $1
  # uncomment to stop the process step by step
  #echo "Press any key to continue..."
  #read -s -n 1
}

# where the dss-container is mounted
dss_mountpath=$1
# the user's chosen subdirectory that is to be shared
subdir=$2

access_to_user=$SUDO_USER
groupname=$(dss_access_group_of "$access_to_user")

groupadd "$groupname"

dir=$(sharedss_dir "$access_to_user")
dssdir="$dss_mountpath/$access_to_user/$subdir"

if [[ ! -d "$dir" ]]
then
  mkdir "$dir" || check_error $LINENO
  wait_input "Created $dir"
else
  echo "Already shared"
  exit 1
fi


chown "$access_to_user:$groupname" "$dir" || check_error_and_cleanup $LINENO

wait_input "Changed ownership to $access_to_user:$groupname"

echo "$dssdir" > "$sharedss_var_lib_mounts/$access_to_user" || check_error_and_cleanup $LINENO
wait_input "Saved settings to $sharedss_var_lib_mounts/$access_to_user"

sudo -u "$access_to_user" bindfs -g "$groupname" -p u=rx,g=rx,o= --realistic-permissions "$dssdir" "$dir" || check_error_and_cleanup $LINENO
wait_input "Bound $dssdir subdirectory to $dir with access allowed for all users in group $groupname"

echo "Success"