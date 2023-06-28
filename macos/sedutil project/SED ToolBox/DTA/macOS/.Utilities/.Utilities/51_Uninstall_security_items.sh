#!/bin/bash

beroot

set +xv

# Source Utility_functions.sh from the same directory as this script
dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
. "${dir}/Utility_functions.sh"


export CA_NAME="Bright Plaza CA"

export KEYCHAIN_NAME="Bright Plaza SED"
export KEYCHAIN_PASSWORD_SERVICE="com.BrightPlaza.SED"
export SERVER_NAME="Bright Plaza SED Server"

export KEYCHAIN_PATH="${SYSTEM_KEYCHAIN_DIR}/${KEYCHAIN_NAME}.keychain"
export KEYCHAIN_PASSWORD_LABEL="${KEYCHAIN_NAME} Keychain"


function file_exists {
    [ -f "${1}" ]
}
export -f file_exists

function SED_keychain_exists {
    file_exists "${KEYCHAIN_PATH}"
}

function read_SED_keychain_password_from_system_keychain {
   2>/dev/null sudo security find-generic-password -l "${KEYCHAIN_PASSWORD_LABEL}" -w "${SYSTEM_KEYCHAIN_PATH}"
}
export -f read_SED_keychain_password_from_system_keychain

function delete_SED_keychain {
    2>/dev/null sudo security delete-keychain  "${KEYCHAIN_PATH}"
}
export -f delete_SED_keychain

function remove_SED_keychain {
    DEBUG_PRINT "remove_SED_keychain"
    SED_keychain_exists  >> "${DEBUGGING_OUTPUT}" 2>&1 || return
    KEYCHAIN_PASSWORD="$( read_SED_keychain_password_from_system_keychain )" \
        || return $(DEBUG_FAILURE_RETURN "finding System keychain item \"${KEYCHAIN_PASSWORD_LABEL}\"")
    unlock_SED_keychain  >> "${DEBUGGING_OUTPUT}" 2>&1 \
        || return $(DEBUG_FAILURE_RETURN "unlocking \"${KEYCHAIN_PATH}\"")
    delete_SED_keychain  >> "${DEBUGGING_OUTPUT}" 2>&1 \
        || return $(DEBUG_FAILURE_RETURN "deleting \"${KEYCHAIN_PATH}\"")
}
export -f remove_SED_keychain

function delete_SED_keychain_password_from_system_keychain {
    security delete-generic-password -l "${KEYCHAIN_PASSWORD_LABEL}"  "${SYSTEM_KEYCHAIN_PATH}"
}
export -f delete_SED_keychain_password_from_system_keychain

function remove_SED_keychain_password {
    DEBUG_PRINT "remove_SED_keychain_password"
    system_keychain_has_SED_keychain_password  >> "${DEBUGGING_OUTPUT}" 2>&1 || return
    delete_SED_keychain_password_from_system_keychain  >> "${DEBUGGING_OUTPUT}" 2>&1 ||
        DEBUG_FAIL "deleting System keychain item \"${KEYCHAIN_PASSWORD_LABEL}\""  $?
}
export -f remove_SED_keychain_password

function remove_CA_cert_from_system_keychain {
    CAFILENAME="${CA_NAME/\*\./}"
    CAFILEPATH="${CERTIFICATES_DIR_PATH}${CAFILENAME}.pem"
    sudo security remove-trusted-cert -d \
         "${CAFILEPATH}"
}
export -f remove_CA_cert_from_system_keychain




DEBUG_PRINT "Removing security items"
remove_SED_keychain  >> "${DEBUGGING_OUTPUT}" 2>&1       \
        || DEBUG_FAIL "removing SED keychain" 10
remove_SED_keychain_password  >> "${DEBUGGING_OUTPUT}" 2>&1       \
        || DEBUG_FAIL "removing SED keychain password from system keychain" 10
remove_CA_cert_from_system_keychain  >> "${DEBUGGING_OUTPUT}" 2>&1       \
        || DEBUG_FAIL "removing CA cert from system keychain" 10
