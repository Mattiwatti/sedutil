/* C:B**************************************************************************
This software is Copyright 2014-2017 Bright Plaza Inc. <drivetrust@drivetrust.com>

This file is part of sedutil.

sedutil is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

sedutil is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with sedutil.  If not, see <http://www.gnu.org/licenses/>.

* C:E********************************************************************** */
#pragma once
#include "os.h"
#include <stdio.h>
#include <iostream>
#pragma warning(push)
#pragma warning(disable : 4091)
#include <Ntddscsi.h>
#pragma warning(pop)
#include <winioctl.h>
#include <vector>
#include "DtaDiskNVMe.h"
#include "DtaEndianFixup.h"
#include "DtaStructures.h"
#include "DtaHexDump.h"

using namespace std;

// Missing stuff pulled from MSDN
//

// STORAGE PROPERTY ID is defined but these #define values are missing
#define StorageAdapterProtocolSpecificProperty (STORAGE_PROPERTY_ID) 49

#define NVME_MAX_LOG_SIZE 4096  // value from random internet search


// End of missing stuff



DtaDiskNVMe::DtaDiskNVMe() {};
void DtaDiskNVMe::init(const char * devref)
{
    LOG(D1) << "Creating DtaDiskNVMe::DtaDiskNVMe() " << devref;

    SDWB * scsi =
        (SDWB *)_aligned_malloc((sizeof(SDWB)), 4096);
    scsiPointer = (void *)scsi;

     hDev = CreateFile(devref,
                      GENERIC_WRITE | GENERIC_READ,
                      FILE_SHARE_WRITE | FILE_SHARE_READ,
                      NULL,
                      OPEN_EXISTING,
                      0,
                      NULL);
    if (INVALID_HANDLE_VALUE == hDev) 
		return;
    else 
        isOpen = TRUE;
}


// Following code thanks to https://github.com/jeffwyeh/sedutil/commit/a8c2a884df706a77f8f03e4f202f9e004d3fd93e
// (Taking advantage of SCSI emulation in Windows NVMe drivers)
uint8_t DtaDiskNVMe::sendCmd(ATACOMMAND cmd, uint8_t protocol, uint16_t comID,
    void * buffer, uint32_t bufferlen)
{
    // Windows structure with 32-bit sense data
    typedef struct
    {
        SCSI_PASS_THROUGH_DIRECT Sptd;
        BYTE sense[32];
    }
    SptdStruct;

    SptdStruct sptdS = { 0 };
    int iRet = 0;
    DWORD bytesReturn = 0;

    LOG(D1) << "Entering DtaDiskNVMe::sendCmd";

    // initialize SCSI CDB
    switch (cmd)
    {
    default:
    {
        return 0xFF;
    }

    case IF_RECV:
    {
        sptdS.Sptd.Cdb[0] = 0xA2;                                /* Opcode */
        sptdS.Sptd.Cdb[1] = protocol;                            /* Security Protocol */
        sptdS.Sptd.Cdb[2] = comID >> 8;                          /* Security Protocol Specific - MSB */
        sptdS.Sptd.Cdb[3] = comID & 0xFF;                        /* Security Protocol Specific - LSB */
        sptdS.Sptd.Cdb[4] = 0x80;                                /* INC 512 */
        sptdS.Sptd.Cdb[6] = (bufferlen / 512) >> 24;             /* Allocation Length - MSB */
        sptdS.Sptd.Cdb[7] = ((bufferlen / 512) >> 16) & 0xFF;
        sptdS.Sptd.Cdb[8] = ((bufferlen / 512) >> 8) & 0xFF;
        sptdS.Sptd.Cdb[9] = (bufferlen / 512) & 0xFF;            /* Allocation Length - LSB */
        break;
    }

    case IF_SEND:
    {
        sptdS.Sptd.Cdb[0] = 0xB5;                                /* Opcode */
        sptdS.Sptd.Cdb[1] = protocol;                            /* Security Protocol */
        sptdS.Sptd.Cdb[2] = comID >> 8;                          /* Security Protocol Specific - MSB */
        sptdS.Sptd.Cdb[3] = comID & 0xFF;                        /* Security Protocol Specific - LSB */
        sptdS.Sptd.Cdb[4] = 0x80;                                /* INC 512 */
        sptdS.Sptd.Cdb[6] = (bufferlen / 512) >> 24;             /* Transfer Length - MSB */
        sptdS.Sptd.Cdb[7] = ((bufferlen / 512) >> 16) & 0xFF;
        sptdS.Sptd.Cdb[8] = ((bufferlen / 512) >> 8) & 0xFF;
        sptdS.Sptd.Cdb[9] = (bufferlen / 512) & 0xFF;            /* Transfer Length - LSB */
        break;
    }
    }

    sptdS.Sptd.Length = sizeof(SCSI_PASS_THROUGH_DIRECT);
    sptdS.Sptd.CdbLength = 12;
    sptdS.Sptd.DataIn = (cmd == IF_RECV) ? SCSI_IOCTL_DATA_IN : SCSI_IOCTL_DATA_OUT;
    sptdS.Sptd.SenseInfoLength = sizeof(sptdS.sense);
    sptdS.Sptd.DataTransferLength = bufferlen;
    sptdS.Sptd.TimeOutValue = 2;
    sptdS.Sptd.DataBuffer = buffer;
    sptdS.Sptd.SenseInfoOffset = offsetof(SptdStruct, sense);

    iRet = DeviceIoControl(hDev,
        IOCTL_SCSI_PASS_THROUGH_DIRECT,
        &sptdS,
        sizeof(sptdS),
        &sptdS,
        sizeof(sptdS),
        &bytesReturn,
        NULL);

    if (0 == iRet)
    {
        LOG(D4) << "cdb after ";
        IFLOG(D4) DtaHexDump(sptdS.Sptd.Cdb, sizeof(sptdS.Sptd.Cdb));
        LOG(D4) << "sense after ";
        IFLOG(D4) DtaHexDump(sptdS.sense, sizeof(sptdS.sense));
        return 0xFF;
    }

    // check for successful target completion
    if (sptdS.Sptd.ScsiStatus != 0)
    {
        LOG(D4) << "cdb after ";
        IFLOG(D4) DtaHexDump(sptdS.Sptd.Cdb, sizeof(sptdS.Sptd.Cdb));
        LOG(D4) << "sense after ";
        IFLOG(D4) DtaHexDump(sptdS.sense, sizeof(sptdS.sense));
        return 0xFF;
    }

    // Success
    return 0x00;
}

void DtaDiskNVMe::identify(OPAL_DiskInfo& disk_info)
{
    LOG(D1) << "Entering DtaDiskNVMe::identify()";
    PVOID   buffer = NULL;
    UINT8   *results = NULL;
    ULONG   bufferLength = 0;
    DWORD dwReturned = 0;
    BOOL iorc = 0;

    PSTORAGE_PROPERTY_QUERY query = NULL;
    PSTORAGE_PROTOCOL_SPECIFIC_DATA protocolData = NULL;
    PSTORAGE_PROTOCOL_DATA_DESCRIPTOR protocolDataDescr = NULL;
    //  This buffer allocation is needed because the STORAGE_PROPERTY_QUERY has additional data
    // that the nvme driver doesn't use ???????????????????
    /* ****************************************************************************************
    !!DANGER WILL ROBINSON!! !!DANGER WILL ROBINSON!! !!DANGER WILL ROBINSON!!
    This buffer definition causes the STORAGE_PROTOCOL_SPECIFIC_DATA to OVERLAY the
    STORAGE_PROPERTY_QUERY.AdditionalParameters field
    * **************************************************************************************** */
    bufferLength = FIELD_OFFSET(STORAGE_PROPERTY_QUERY, AdditionalParameters)
        + sizeof(STORAGE_PROTOCOL_SPECIFIC_DATA) + NVME_MAX_LOG_SIZE;
    buffer = malloc(bufferLength);
    /* */
    if (buffer == NULL) {
        LOG(E) << "DeviceNVMeQueryProtocolDataTest: allocate buffer failed, exit.\n";
        return;
    }

    //
    // Initialize query data structure to get Identify Data.
    //
    ZeroMemory(buffer, bufferLength);

    query = (PSTORAGE_PROPERTY_QUERY)buffer;
    /* ****************************************************************************************
    !!DANGER WILL ROBINSON!! !!DANGER WILL ROBINSON!! !!DANGER WILL ROBINSON!!
    This buffer definition causes the STORAGE_PROTOCOL_SPECIFIC_DATA to OVERLAY the
    STORAGE_PROPERTY_QUERY.AdditionalParameters field
    * **************************************************************************************** */
    protocolDataDescr = (PSTORAGE_PROTOCOL_DATA_DESCRIPTOR)buffer;
    protocolData = (PSTORAGE_PROTOCOL_SPECIFIC_DATA)query->AdditionalParameters;
    /* */
    query->PropertyId = StorageAdapterProtocolSpecificProperty;
    query->QueryType = PropertyStandardQuery;

    protocolData->ProtocolType = ProtocolTypeNvme;
    protocolData->DataType = NVMeDataTypeIdentify;
    //	protocolData->ProtocolDataRequestValue = NVME_IDENTIFY_CNS_CONTROLLER;
    protocolData->ProtocolDataRequestSubValue = 0;
    protocolData->ProtocolDataOffset = sizeof(STORAGE_PROTOCOL_SPECIFIC_DATA);
    protocolData->ProtocolDataLength = NVME_MAX_LOG_SIZE;

    iorc = DeviceIoControl(hDev, IOCTL_STORAGE_QUERY_PROPERTY,
        buffer, bufferLength, buffer, bufferLength, &dwReturned, NULL);

    //
    //
    //
    disk_info.devType = DEVICE_TYPE_NVME;
    results = (UINT8 *)buffer + FIELD_OFFSET(STORAGE_PROPERTY_QUERY, AdditionalParameters)
        + sizeof(STORAGE_PROTOCOL_SPECIFIC_DATA);
    results += 4;
    memcpy(disk_info.serialNum, results, sizeof(disk_info.serialNum));
    results += sizeof(disk_info.serialNum);
    memcpy(disk_info.modelNum, results, sizeof(disk_info.modelNum));
    results += sizeof(disk_info.modelNum);
    memcpy(disk_info.firmwareRev, results, sizeof(disk_info.firmwareRev));


    return;
}

/** Close the filehandle so this object can be delete. */
DtaDiskNVMe::~DtaDiskNVMe()
{
    LOG(D1) << "Destroying DtaDiskNVMe";
    CloseHandle(hDev);

}
