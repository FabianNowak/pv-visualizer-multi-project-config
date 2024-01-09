#!/bin/bash
# shared definitions for all sharedss scripts 

dss_access_group_of() {
    username="$1"
    echo "dss-access-$username"
}

sharedss_dir() {
    username="$1"
    echo "/sharedss/$username"
}

sharedss_var_lib_mounts="/var/lib/sharedss/mounts"