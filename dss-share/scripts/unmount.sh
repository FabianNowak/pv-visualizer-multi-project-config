#!/bin/bash

source $(dirname "$0")/definitions.sh

calleruser=$SUDO_USER

groupname=$(dss_access_group_of "$calleruser")
dir=$(sharedss_dir "$calleruser")

# get comma delimited list of all members
members=$(getent group "$groupname" | awk -F: '{print $NF}')

#replace , with space
for member in ${members//,/ }
do
    echo "Revoking access for $member"
    deluser "$member" "$groupname"
done

rm "$sharedss_var_lib_mounts/$calleruser"
fusermount -u "$dir"
rm -d "$dir"

echo "Success"