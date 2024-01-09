#!/bin/bash

source $(dirname "$0")/definitions.sh

calleruser=$SUDO_USER
username=$1

groupname=$(dss_access_group_of "$calleruser")

deluser "$username" "$groupname"