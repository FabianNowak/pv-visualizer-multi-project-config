#!/bin/bash

source $(dirname "$0")/definitions.sh

username=$SUDO_USER

groupname=$(dss_access_group_of "$username")

getent group "$groupname" | awk -F: '{print $NF}'