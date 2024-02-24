/* C:B**************************************************************************
   This software is Copyright (c) 2014-2024 Bright Plaza Inc. <drivetrust@drivetrust.com>

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
#include "os.h"
#include <malloc.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <arpa/inet.h>
#include <scsi/sg.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <linux/hdreg.h>
#include <errno.h>
#include <vector>
#include <fstream>
#include "DtaDevLinuxSata.h"
#include "DtaHexDump.h"
#include "ParseATIdentify.h"

//
// taken from <scsi/scsi.h> to avoid SCSI/ATA name collision
//


bool DtaDevLinuxSata::identifyUsingATAIdentifyDevice(int fd,
                                                     InterfaceDeviceID & interfaceDeviceIdentification,
                                                     DTA_DEVICE_INFO & disk_info,
                                                     dictionary ** ppIdentifyCharacteristics) {

  // Test whether device is a SAT drive by attempting
  // SCSI passthrough of ATA Identify Device command
  // If it works, as a side effect, parse the Identify response

  bool isSAT = false;
  void * identifyDeviceResponse = aligned_alloc(IO_BUFFER_ALIGNMENT, MIN_BUFFER_LENGTH);
  if ( identifyDeviceResponse == NULL ) {
    LOG(E) << " *** memory buffer allocation failed *** !!!";
    return false;
  }
#define IDENTIFY_RESPONSE_SIZE 512
  bzero ( identifyDeviceResponse, IDENTIFY_RESPONSE_SIZE );

  unsigned int dataLen = IDENTIFY_RESPONSE_SIZE;
  LOG(D4) << "Invoking identifyDevice_SAT --  dataLen=" << std::hex << "0x" << dataLen ;
  isSAT = (0 == identifyDevice_SAT( fd, identifyDeviceResponse, dataLen ));

  if (isSAT) {
    LOG(D4) << " identifyDevice_SAT returned zero -- is SAT" ;

    if (0xA5==((uint8_t *)identifyDeviceResponse)[510]) {  // checksum is present
      uint8_t checksum=0;
      for (uint8_t * p = ((uint8_t *)identifyDeviceResponse),
             * end = ((uint8_t *)identifyDeviceResponse) + 512;
           p<end ;
           p++)
        checksum=(uint8_t)(checksum+(*p));
      if (checksum != 0) {
        LOG(D1) << " *** IDENTIFY DEVICE response checksum failed *** !!!" ;
      }
    } else {
      LOG(D4) << " *** IDENTIFY DEVICE response checksum not present" ;
    }
    IFLOG(D4) {
      LOG(D4) << "ATA IDENTIFY DEVICE response: dataLen=" << std::hex << "0x" << dataLen ;
      DtaHexDump(identifyDeviceResponse, dataLen);
    }

    dictionary *pIdentifyCharacteristics =
      parseATAIdentifyDeviceResponse(interfaceDeviceIdentification,
                                     ((uint8_t *)identifyDeviceResponse),
                                     disk_info);
    if (ppIdentifyCharacteristics != NULL)
      (*ppIdentifyCharacteristics) = pIdentifyCharacteristics;
    else if (pIdentifyCharacteristics !=NULL)
      delete pIdentifyCharacteristics;
  } else {
    LOG(D4) << " identifyDevice_SAT returned non-zero -- is not SAT" ;
  }
  free(identifyDeviceResponse);

  return isSAT;
}



int DtaDevLinuxSata::identifyDevice_SAT( int fd, void * buffer , unsigned int & dataLength)
{

  //  *** TODO ***   sg.timeout = 600; // Sabrent USB-SATA adapter 1ms,6ms,20ms,60 NG, 600ms OK
  LOG(D4) << " identifyDevice_SAT about to PerformATAPassThroughCommand" ;
  unsigned char sense[32];
  unsigned char senselen=sizeof(sense);
  unsigned char masked_status;
  int result=PerformATAPassThroughCommand(fd,
                                          IDENTIFY, 0, 0,
                                          buffer, dataLength,
                                          sense, senselen,
                                          &masked_status);
  IFLOG(D4) {
    LOG(D4) << "identifyDevice_SAT: result=" << result << " dataLength=" << std::hex << "0x" << dataLength ;
    LOG(D4) << "sense after" ;
    DtaHexDump(sense, senselen);
    LOG(D4) << "masked_status " << statusName( masked_status );
    if (0==result)
      DtaHexDump(buffer, dataLength);
  }
  return result;
}


int DtaDevLinuxSata::PerformATAPassThroughCommand(int fd,
                                                  int cmd, int securityProtocol, int comID,
                                                  void * buffer,  unsigned int & bufferlen,
                                                  unsigned char * sense, unsigned char & senselen,
                                                  unsigned char * pmasked_status)
{
  uint8_t protocol;
  int dxfer_direction;

  switch (cmd)
    {
    case IDENTIFY:
    case IF_RECV:
      protocol = PIO_DATA_IN;
      dxfer_direction = SG_DXFER_FROM_DEV;
      break;

    case IF_SEND:
      protocol = PIO_DATA_OUT;
      dxfer_direction = SG_DXFER_TO_DEV;
      break;

    default:
      LOG(E) << "Exiting DtaDevLinuxSata::PerformATAPassThroughCommand because of unrecognized cmd=" << cmd << "?!" ;
      return 0xff;
    }


  CScsiCmdATAPassThrough_12 cdb;
  uint8_t * cdbBytes=(uint8_t *)&cdb;  // We use direct byte pointer because bitfields are unreliable
  cdbBytes[1] = protocol << 1;
  cdbBytes[2] = (protocol==PIO_DATA_IN ? 1 : 0) << 3 |  // TDir
                1                               << 2 |  // ByteBlock
                2                                       // TLength  10b => transfer length in Count
                ;
  cdb.m_Features = securityProtocol;
  cdb.m_Count = bufferlen/512;
  cdb.m_LBA_Mid = comID & 0xFF;          // ATA lbaMid   / TRUSTED COMID low
  cdb.m_LBA_High = (comID >> 8) & 0xFF; // ATA lbaHihg  / TRUSTED COMID high
  cdb.m_Command = cmd;

  int result=DtaDevLinuxScsi::PerformSCSICommand(fd,
                                                 dxfer_direction,
                                                 cdbBytes, (unsigned char)sizeof(cdb),
                                                 buffer, bufferlen,
                                                 sense, senselen,
                                                 pmasked_status);
  return result;
}




dictionary *
DtaDevLinuxSata::parseATAIdentifyDeviceResponse(const InterfaceDeviceID & interfaceDeviceIdentification,
                                                const unsigned char * response,
                                                DTA_DEVICE_INFO & di)
{
  if (NULL == response)
    return NULL;

  const IDENTIFY_RESPONSE & resp = *(IDENTIFY_RESPONSE *)response;

  parseATIdentifyResponse(&resp, &di);

  if (deviceNeedsSpecialAction(interfaceDeviceIdentification,
                               splitVendorNameFromModelNumber)) {
    LOG(D4) << " *** splitting VendorName from ModelNumber";
    LOG(D4) << " *** was vendorID=\"" << di.vendorID << "\" modelNum=\"" <<  di.modelNum << "\"";
    memcpy(di.vendorID, di.modelNum, sizeof(di.vendorID));
    memmove(di.modelNum,
            di.modelNum+sizeof(di.vendorID),
            sizeof(di.modelNum)-sizeof(di.vendorID));
    memset(di.modelNum+sizeof(di.modelNum)-sizeof(di.vendorID),
           0,
           sizeof(di.vendorID));
    LOG(D4) << " *** now vendorID=\"" << di.vendorID << "\" modelNum=\"" <<  di.modelNum << "\"";
  }


  std::ostringstream ss1;
  ss1 << "0x" << std::hex << std::setw(4) << std::setfill('0');
  ss1 << (int)(resp.TCGOptions[1]<<8 | resp.TCGOptions[0]);;
  std::string options = ss1.str();

  std::ostringstream ss;
  ss << std::hex << std::setw(2) << std::setfill('0');
  for (uint8_t &b: di.worldWideName) ss << (int)b;
  std::string wwn = ss.str();
  return new dictionary
    {
      {"TCG Options"       , options                        },
      {"Device Type"       , resp.devType ? "OTHER" : "ATA" },
      {"Serial Number"     , (const char *)di.serialNum     },
      {"Model Number"      , (const char *)di.modelNum      },
      {"Firmware Revision" , (const char *)di.firmwareRev   },
      {"World Wide Name"   , wwn                            },
    };
}



/** Send an ioctl to the device using pass through. */
uint8_t DtaDevLinuxSata::sendCmd(ATACOMMAND cmd, uint8_t securityProtocol, uint16_t comID,
                                 void * buffer, uint32_t bufferlen)
{
  LOG(D1) << "Entering DtaDevLinuxSata::sendCmd";

  unsigned char sense[32];
  unsigned char senselen=sizeof(sense);
  bzero(&sense, senselen);

  unsigned int dataLength = bufferlen;
  unsigned char masked_status=GOOD;
  /*
   * Do the IO
   */
  int result= PerformATAPassThroughCommand(fd, cmd, securityProtocol, comID,
                                           buffer, dataLength,
                                           sense, senselen,
                                           &masked_status);

  if (result < 0) {
    LOG(D4) << "PerformATAPassThroughCommand returned " << result;
    LOG(D4) << "sense after ";
    IFLOG(D4) DtaHexDump(&sense, senselen);
    return 0xff;
  }

  LOG(D4) << "PerformATAPassThroughCommand returned " << result;
  LOG(D4) << "sense after ";
  IFLOG(D4) DtaHexDump(&sense, senselen);

  // check for successful target completion
  if (masked_status != GOOD)
    {
      LOG(D4) << "masked_status=" << masked_status << "=" << statusName(masked_status) << " != GOOD  cmd=" <<
        (cmd == IF_SEND ? std::string("IF_SEND") :
         cmd == IF_RECV ? std::string("IF_RECV") :
         cmd == IDENTIFY ? std::string("IDENTIFY") :
         std::to_string(cmd));
      LOG(D4) << "sense after ";
      IFLOG(D4) DtaHexDump(&sense, senselen);
      return 0xff;
    }

  if (! ((0x00 == sense[0]) && (0x00 == sense[1])) ||
      ((0x72 == sense[0]) && (0x0b == sense[1])) ) {
    LOG(D4) << "PerformATAPassThroughCommand disqualifying ATA response --"
            << " sense[0]=0x" << std::hex << sense[0]
            << " sense[1]=0x" << std::hex << sense[1];
    return 0xff; // not ATA response
  }

  LOG(D4) << "buffer after ";
  IFLOG(D4) DtaHexDump(buffer, dataLength);
  LOG(D4) << "PerformATAPassThroughCommand returning sense[11]=0x" << std::hex << sense[11];
  return (sense[11]);
}


bool  DtaDevLinuxSata::identify(DTA_DEVICE_INFO& disk_info)
{
  InterfaceDeviceID interfaceDeviceIdentification;
  return identifyUsingATAIdentifyDevice(fd, interfaceDeviceIdentification, disk_info, NULL);
}






#if NO_LONGER_NEEDED



// This version I just rescued from /tmp at Sun Feb 18 11:07:38 PM EST 2024

uint8_t DtaDevLinuxSata::sendCmd_Sata(ATACOMMAND cmd, uint8_t protocol, uint16_t comID,
                                      void * buffer, uint32_t bufferlen)
{
  sg_io_hdr_t sg;
  uint8_t sense[32]; // how big should this be??
  uint8_t cdb[12];

  LOG(D1) << "Entering DtaDevLinuxScsi::sendCmd";
  memset(&cdb, 0, sizeof (cdb));
  memset(&sense, 0, sizeof (sense));
  memset(&sg, 0, sizeof (sg));
  /*
   * Initialize the CDB as described in ScsiT-2 and the
   * ATA Command set reference (protocol and commID placement)
   * We need a few more standards bodies --NOT--
   */

  cdb[0] = 0xa1; // ata pass through(12)
  /*
   * Byte 1 is the protocol 4 = PIO IN and 5 = PIO OUT
   * Byte 2 is:
   * bits 7-6 OFFLINE - Amount of time the command can take the bus offline
   * bit 5    CK_COND - If set the command will always return a condition check
   * bit 4    RESERVED
   * bit 3    T_DIR   - transfer direction 1 in, 0 out
   * bit 2    BYTE_BLock  1 = transfer in blocks, 0 transfer in bytes
   * bits 1-0 T_LENGTH -  10 = the length id in sector count
   */
  sg.timeout = 60000;
  if (IF_RECV == cmd) {
    // how do I know it is discovery 0 ?
    cdb[1] = 4 << 1; // PIO DATA IN
    cdb[2] = 0x0E; // T_DIR = 1, BYTE_BLOCK = 1, Length in Sector Count
    cdb[4] = bufferlen / 512; // Sector count / transfer length (512b blocks)
    sg.dxfer_direction = SG_DXFER_FROM_DEV;
    sg.dxfer_len = bufferlen;
  }
  else if (IDENTIFY == cmd) {
    sg.timeout = 600; // Sabrent USB-ScsiTA adapter 1ms,6ms,20ms,60 NG, 600ms OK
    cdb[1] = 4 << 1; // PIO DATA IN
    cdb[2] = 0x0E; // T_DIR = 1, BYTE_BLOCK = 1, Length in Sector Count
    cdb[4] = 1; // Sector count / transfer length (512b blocks)
    sg.dxfer_direction = SG_DXFER_FROM_DEV;
    sg.dxfer_len = 512; // if not exactly 512-byte, exteremly long timeout, 2 - 3 minutes
  }
  else {
    cdb[1] = 5 << 1; // PIO DATA OUT
    cdb[2] = 0x06; // T_DIR = 0, BYTE_BLOCK = 1, Length in Sector Count
    cdb[4] = bufferlen / 512; // Sector count / transfer length (512b blocks)
    sg.dxfer_direction = SG_DXFER_TO_DEV;
    sg.dxfer_len = bufferlen;
  }
  cdb[3] = protocol; // ATA features / TRUSTED S/R security protocol
  cdb[4] = bufferlen / 512; // Sector count / transfer length (512b blocks)
  //      cdb[5] = reserved;
  cdb[7] = ((comID & 0xff00) >> 8);
  cdb[6] = (comID & 0x00ff);
  //      cdb[8] = 0x00;              // device
  cdb[9] = cmd; // IF_SEND/IF_RECV
  //      cdb[10] = 0x00;              // reserved
  //      cdb[11] = 0x00;              // control
  /*
   * Set up the SCSI Generic structure
   * see the SG HOWTO for the best info I could find
   */
  sg.interface_id = 'S';
  //      sg.dxfer_direction = Set in if above
  sg.cmd_len = sizeof (cdb);
  sg.mx_sb_len = sizeof (sense);
  sg.iovec_count = 0;
  sg.dxfer_len = bufferlen;
  sg.dxferp = buffer;
  sg.cmdp = cdb;
  sg.sbp = sense;
  //sg.timeout = 60000;
  sg.flags = 0;
  sg.pack_id = 0;
  sg.usr_ptr = NULL;
  //    LOG(D4) << "cdb before ";
  //    IFLOG(D4) DtaHexDump(cdb, sizeof (cdb));
  //    LOG(D4) << "sg before ";
  //    IFLOG(D4) DtaHexDump(&sg, sizeof (sg));
  /*
   * Do the IO
   */
  if (ioctl(fd, SG_IO, &sg) < 0) {
    //    LOG(D4) << "cdb after ";
    //    IFLOG(D4) DtaHexDump(cdb, sizeof (cdb));
    //    LOG(D4) << "sense after ";
    //    IFLOG(D4) DtaHexDump(sense, sizeof (sense));
    return 0xff;
  }
  //    LOG(D4) << "cdb after ";
  //    IFLOG(D4) DtaHexDump(cdb, sizeof (cdb));
  //    LOG(D4) << "sg after ";
  //    IFLOG(D4) DtaHexDump(&sg, sizeof (sg));
  //    LOG(D4) << "sense after ";
  //    IFLOG(D4) DtaHexDump(sense, sizeof (sense));
  if (!((0x00 == sense[0]) && (0x00 == sense[1])))
    if (!((0x72 == sense[0]) && (0x0b == sense[1]))) return 0xff; // not ATA response
  return (sense[11]);
}








































using namespace std;

/** The Device class represents a single disk device.
 *  Linux specific implementation using the SCSI generic interface and
 *  SCSI ATA Pass Through (12) command
 */
DtaDevLinuxSata::DtaDevLinuxSata() {
  isSAS = 0;
}

bool DtaDevLinuxSata::init(const char * devref)
{
  LOG(D1) << "Creating DtaDevLinuxSata::DtaDev() " << devref;
  bool isOpen = FALSE;

  if (access(devref, R_OK | W_OK)) {
    LOG(E) << "You do not have permission to access the raw disk in write mode";
    LOG(E) << "Perhaps you might try sudo to run as root";
  }

  if ((fd = open(devref, O_RDWR)) < 0) {
    isOpen = FALSE;
    // This is a D1 because diskscan looks for open fail to end scan
    LOG(D1) << "Error opening device " << devref << " " << (int32_t) fd;
    //        if (-EPERM == fd) {
    //            LOG(E) << "You do not have permission to access the raw disk in write mode";
    //            LOG(E) << "Perhaps you might try sudo to run as root";
    //        }
  }
  else {
    isOpen = TRUE;
  }
  return isOpen;
}

/** Send an ioctl to the device using pass through. */
uint8_t DtaDevLinuxSata::sendCmd(ATACOMMAND cmd, uint8_t protocol, uint16_t comID,
                                 void * buffer, uint32_t bufferlen)
{
  if(isSAS) {
    return(sendCmd_SAS(cmd, protocol, comID, buffer, bufferlen));
  }
  sg_io_hdr_t sg;
  uint8_t sense[32]; // how big should this be??
  uint8_t cdb[12];

  LOG(D1) << "Entering DtaDevLinuxSata::sendCmd";
  memset(&cdb, 0, sizeof (cdb));
  memset(&sense, 0, sizeof (sense));
  memset(&sg, 0, sizeof (sg));
  /*
   * Initialize the CDB as described in SAT-2 and the
   * ATA Command set reference (protocol and commID placement)
   * We need a few more standards bodies --NOT--
   */

  cdb[0] = 0xa1; // ata pass through(12)
  /*
   * Byte 1 is the protocol 4 = PIO IN and 5 = PIO OUT
   * Byte 2 is:
   * bits 7-6 OFFLINE - Amount of time the command can take the bus offline
   * bit 5    CK_COND - If set the command will always return a condition check
   * bit 4    RESERVED
   * bit 3    T_DIR   - transfer direction 1 in, 0 out
   * bit 2    BYTE_BLock  1 = transfer in blocks, 0 transfer in bytes
   * bits 1-0 T_LENGTH -  10 = the length id in sector count
   */
  sg.timeout = 60000;
  if (IF_RECV == cmd) {
    // how do I know it is discovery 0 ?
    cdb[1] = 4 << 1; // PIO DATA IN
    cdb[2] = 0x0E; // T_DIR = 1, BYTE_BLOCK = 1, Length in Sector Count
    cdb[4] = bufferlen / 512; // Sector count / transfer length (512b blocks)
    sg.dxfer_direction = SG_DXFER_FROM_DEV;
    sg.dxfer_len = bufferlen;
  }
  else if (IDENTIFY == cmd) {
    sg.timeout = 600; // Sabrent USB-SATA adapter 1ms,6ms,20ms,60 NG, 600ms OK
    cdb[1] = 4 << 1; // PIO DATA IN
    cdb[2] = 0x0E; // T_DIR = 1, BYTE_BLOCK = 1, Length in Sector Count
    cdb[4] = 1; // Sector count / transfer length (512b blocks)
    sg.dxfer_direction = SG_DXFER_FROM_DEV;
    sg.dxfer_len = 512; // if not exactly 512-byte, exteremly long timeout, 2 - 3 minutes
  }
  else {
    cdb[1] = 5 << 1; // PIO DATA OUT
    cdb[2] = 0x06; // T_DIR = 0, BYTE_BLOCK = 1, Length in Sector Count
    cdb[4] = bufferlen / 512; // Sector count / transfer length (512b blocks)
    sg.dxfer_direction = SG_DXFER_TO_DEV;
    sg.dxfer_len = bufferlen;
  }
  cdb[3] = protocol; // ATA features / TRUSTED S/R security protocol
  cdb[4] = bufferlen / 512; // Sector count / transfer length (512b blocks)
  //      cdb[5] = reserved;
  cdb[7] = ((comID & 0xff00) >> 8);
  cdb[6] = (comID & 0x00ff);
  //      cdb[8] = 0x00;              // device
  cdb[9] = cmd; // IF_SEND/IF_RECV
  //      cdb[10] = 0x00;              // reserved
  //      cdb[11] = 0x00;              // control
  /*
   * Set up the SCSI Generic structure
   * see the SG HOWTO for the best info I could find
   */
  sg.interface_id = 'S';
  //      sg.dxfer_direction = Set in if above
  sg.cmd_len = sizeof (cdb);
  sg.mx_sb_len = sizeof (sense);
  sg.iovec_count = 0;
  sg.dxfer_len = bufferlen;
  sg.dxferp = buffer;
  sg.cmdp = cdb;
  sg.sbp = sense;
  //sg.timeout = 60000;
  sg.flags = 0;
  sg.pack_id = 0;
  sg.usr_ptr = NULL;
  //    LOG(D4) << "cdb before ";
  //    IFLOG(D4) DtaHexDump(cdb, sizeof (cdb));
  //    LOG(D4) << "sg before ";
  //    IFLOG(D4) DtaHexDump(&sg, sizeof (sg));
  /*
   * Do the IO
   */
  if (ioctl(fd, SG_IO, &sg) < 0) {
    //    LOG(D4) << "cdb after ";
    //    IFLOG(D4) DtaHexDump(cdb, sizeof (cdb));
    //    LOG(D4) << "sense after ";
    //    IFLOG(D4) DtaHexDump(sense, sizeof (sense));
    return 0xff;
  }
  //    LOG(D4) << "cdb after ";
  //    IFLOG(D4) DtaHexDump(cdb, sizeof (cdb));
  //    LOG(D4) << "sg after ";
  //    IFLOG(D4) DtaHexDump(&sg, sizeof (sg));
  //    LOG(D4) << "sense after ";
  //    IFLOG(D4) DtaHexDump(sense, sizeof (sense));
  if (!((0x00 == sense[0]) && (0x00 == sense[1])))
    if (!((0x72 == sense[0]) && (0x0b == sense[1]))) return 0xff; // not ATA response
  return (sense[11]);
}

bool DtaDevLinuxSata::identify(DTA_DEVICE_INFO& disk_info)
{
  LOG(D1) << "Entering DtaDevLinuxSata::identify";
  sg_io_hdr_t sg;
  uint8_t sense[32]; // how big should this be??
  uint8_t cdb[12];
  memset(&cdb, 0, sizeof (cdb));
  memset(&sense, 0, sizeof (sense));
  memset(&sg, 0, sizeof (sg));
  LOG(D4) << "Entering DtaDevLinuxSata::identify()";
  // uint8_t bus_sas = 0;
  vector<uint8_t> nullz(512, 0x00);
  uint8_t * buffer = (uint8_t *) memalign(IO_BUFFER_ALIGNMENT, MIN_BUFFER_LENGTH);
  memset(buffer, 0, MIN_BUFFER_LENGTH);
  /*
   * Initialize the CDB as described in SAT-2 and the
   * ATA Command set reference (protocol and commID placement)
   * We need a few more standards bodies --NOT--
   */

  cdb[0] = 0xa1; // ata pass through(12)
  /*
   * Byte 1 is the protocol 4 = PIO IN and 5 = PIO OUT
   * Byte 2 is:
   * bits 7-6 OFFLINE - Amount of time the command can take the bus offline
   * bit 5    CK_COND - If set the command will always return a condition check
   * bit 4    RESERVED
   * bit 3    T_DIR   - transfer direction 1 in, 0 out
   * bit 2    BYTE_BLock  1 = transfer in blocks, 0 transfer in bytes
   * bits 1-0 T_LENGTH -  10 = the length id in sector count
   */
  cdb[1] = 4 << 1; // PIO DATA IN
  cdb[2] = 0x0E; // T_DIR = 1, BYTE_BLOCK = 1, Length in Sector Count
  sg.dxfer_direction = SG_DXFER_FROM_DEV;
  cdb[4] = 1;
  cdb[9] = 0xec; // IF_SEND/IF_RECV
  //      cdb[10] = 0x00;              // reserved
  //      cdb[11] = 0x00;              // control
  /*
   * Set up the SCSI Generic structure
   * see the SG HOWTO for the best info I could find
   */
  sg.interface_id = 'S';
  //      sg.dxfer_direction = Set in if above
  sg.cmd_len = sizeof (cdb);
  sg.mx_sb_len = sizeof (sense);
  sg.iovec_count = 0;
  sg.dxfer_len = 512;
  sg.dxferp = buffer;
  sg.cmdp = cdb;
  sg.sbp = sense;
  sg.timeout = 60000;
  sg.flags = 0;
  sg.pack_id = 0;
  sg.usr_ptr = NULL;
  //    LOG(D4) << "cdb before ";
  //    IFLOG(D4) hexDump(cdb, sizeof (cdb));
  //    LOG(D4) << "sg before ";
  //    IFLOG(D4) hexDump(&sg, sizeof (sg));
  /*
   * Do the IO
   */
  if (ioctl(fd, SG_IO, &sg) < 0) {
    LOG(D4) << "cdb after ";
    IFLOG(D4) DtaHexDump(cdb, sizeof (cdb));
    LOG(D4) << "sense after ";
    IFLOG(D4) DtaHexDump(sense, sizeof (sense));
    disk_info.devType = DEVICE_TYPE_OTHER;
    sendCmd(IDENTIFY, 0, 0, buffer, IO_BUFFER_LENGTH);
    // bus_sas =1;
  }

  uint8_t result;
  result = sendCmd(IDENTIFY, 0, 0, buffer, 512 );
  if (result) {
    LOG(D1) << "Exiting DtaDevLinuxSata::identify (1)";
    return false;
  }





  //    LOG(D4) << "cdb after ";
  //    IFLOG(D4) hexDump(cdb, sizeof (cdb));
  //    LOG(D4) << "sg after ";
  //    IFLOG(D4) hexDump(&sg, sizeof (sg));
  //    LOG(D4) << "sense after ";
  //    IFLOG(D4) hexDump(sense, sizeof (sense));

  ifstream kopts;
  kopts.open("/sys/module/libata/parameters/allow_tpm", ios::in);
  if (!kopts) {
    LOG(W) << "Unable to verify Kernel flag libata.allow_tpm ";
    break;
  }
}
if (nonp) memset(disk_info.modelNum,0,sizeof(disk_info.modelNum));
free(buffer);


// TODO: Also do discovery0 here.

LOG(D1) << "Exiting DtaDevLinuxSata::identify (3)";
return true;
}


/** Send an ioctl to the device using pass through. */
uint8_t DtaDevLinuxSata::sendCmd_SAS(ATACOMMAND cmd, uint8_t protocol, uint16_t comID,
                                     void * buffer, uint32_t bufferlen)
{
  sg_io_hdr_t sg;
  uint8_t sense[32]; // how big should this be??
  uint8_t cdb[12];

  LOG(D1) << "Entering DtaDevLinuxSara::sendCmd_SAS";
  memset(&cdb, 0, sizeof (cdb));
  memset(&sense, 0, sizeof (sense));
  memset(&sg, 0, sizeof (sg));


  LOG(D4) << "sizeof(unsigned)=" << sizeof(unsigned) << " sizeof(uint8_t)=" << sizeof(uint8_t) << " sizeof(uint16_t)=" << sizeof(uint16_t);

  // initialize SCSI CDB
  switch(cmd)
    {/* JERRY
        default:
        {
        return 0xff;
        }
     */
    case IF_RECV:
      {
        auto * p = (CScsiCmdSecurityProtocolIn *) cdb;
        p->m_Opcode = p->OPCODE;
        p->m_SecurityProtocol = protocol;
        p->m_SecurityProtocolSpecific = htons(comID);
        //p->m_INC_512 = 1;
        //p->m_AllocationLength = htonl(bufferlen/512);
        p->m_INC_512 = 0;
        p->m_AllocationLength = htonl(bufferlen);
        break;
      }
    case IF_SEND:
      {
        auto * p = (CScsiCmdSecurityProtocolOut *) cdb;
        p->m_Opcode = p->OPCODE;
        p->m_SecurityProtocol = protocol;
        p->m_SecurityProtocolSpecific = htons(comID);
        //p->m_INC_512 = 1;
        //p->m_TransferLength = htonl(bufferlen/512);
        p->m_INC_512 = 0;
        p->m_TransferLength = htonl(bufferlen);
        break;
      }
    case IDENTIFY:
      {
        return 0xff;
      }
    default:
      {
        return 0xff;
      }
    }

  // fill out SCSI Generic structure
  sg.interface_id = 'S';
  sg.dxfer_direction = (cmd == IF_RECV) ? SG_DXFER_FROM_DEV : SG_DXFER_TO_DEV;
  sg.cmd_len = sizeof (cdb);
  sg.mx_sb_len = sizeof (sense);
  sg.iovec_count = 0;
  sg.dxfer_len = bufferlen;
  sg.dxferp = buffer;
  sg.cmdp = cdb;
  sg.sbp = sense;
  sg.timeout = 60000;
  sg.flags = 0;
  sg.pack_id = 0;
  sg.usr_ptr = NULL;

  // execute I/O
  if (ioctl(fd, SG_IO, &sg) < 0) {
    LOG(D4) << "cdb after ioctl(fd, SG_IO, &sg) cmd( " << cmd ;
    IFLOG(D4) DtaHexDump(cdb, sizeof (cdb));
    LOG(D4) << "sense after ";
    IFLOG(D4) DtaHexDump(sense, sizeof (sense));
    return 0xff;
  }

  // check for successful target completion
  if (sg.masked_status != GOOD)
    {
      LOG(D4) << "cdb after sg.masked_status != GOOD cmd " << cmd;
      IFLOG(D4) DtaHexDump(cdb, sizeof (cdb));
      LOG(D4) << "sense after ";
      IFLOG(D4) DtaHexDump(sense, sizeof (sense));
      return 0xff;
    }

  // success
  return 0;
}

static void safecopy(uint8_t * dst, size_t dstsize, uint8_t * src, size_t srcsize)
{
  const size_t size = min(dstsize, srcsize);
  if (size > 0) memcpy(dst, src, size);
  if (size < dstsize) memset(dst+size, '\0', dstsize-size);
}

void DtaDevLinuxSata::identify_SAS(DTA_DEVICE_INFO *disk_info)
{
  sg_io_hdr_t sg;
  uint8_t sense[18];
  uint8_t cdb[sizeof(CScsiCmdInquiry)];

  LOG(D4) << "Entering DtaDevLinuxSata::identify_SAS()";
  uint8_t * buffer = (uint8_t *) aligned_alloc(IO_BUFFER_ALIGNMENT, MIN_BUFFER_LENGTH);

  memset(&cdb, 0, sizeof (cdb));
  memset(&sense, 0, sizeof (sense));
  memset(&sg, 0, sizeof (sg));

  // fill out SCSI command
  auto p = (CScsiCmdInquiry *) cdb;
  p->m_Opcode = p->OPCODE;
  p->m_AllocationLength = htons(sizeof(CScsiCmdInquiry_StandardData));

  // fill out SCSI Generic structure
  sg.interface_id = 'S';
  sg.dxfer_direction = SG_DXFER_FROM_DEV;
  sg.cmd_len = sizeof (cdb);
  sg.mx_sb_len = sizeof (sense);
  sg.iovec_count = 0;
  sg.dxfer_len = MIN_BUFFER_LENGTH;
  sg.dxferp = buffer;
  sg.cmdp = cdb;
  sg.sbp = sense;
  sg.timeout = 60000;
  sg.flags = 0;
  sg.pack_id = 0;
  sg.usr_ptr = NULL;

  // execute I/O
  if (ioctl(fd, SG_IO, &sg) < 0) {
    LOG(D4) << "cdb after ioctl(fd, SG_IO, &sg)";
    IFLOG(D4) DtaHexDump(cdb, sizeof (cdb));
    LOG(D4) << "sense after ";
    IFLOG(D4) DtaHexDump(sense, sizeof (sense));
    disk_info->devType = DEVICE_TYPE_OTHER;
    free(buffer);
    return;
  }

  // check for successful target completion
  if (sg.masked_status != GOOD)
    {
      LOG(D4) << "cdb after sg.masked_status != GOOD";
      IFLOG(D4) DtaHexDump(cdb, sizeof (cdb));
      LOG(D4) << "sense after ";
      IFLOG(D4) DtaHexDump(sense, sizeof (sense));
      disk_info->devType = DEVICE_TYPE_OTHER;
      free(buffer);
      return;
    }

  // response is a standard INQUIRY (at least 36 bytes)
  auto resp = (CScsiCmdInquiry_StandardData *) buffer;

  // make sure SCSI target is disk
  if (((sg.dxfer_len - sg.resid) < sizeof(CScsiCmdInquiry_StandardData)) // some drive return more than sizeof(CScsiCmdInquiry_StandardData)
      || (resp->m_PeripheralDeviceType != 0x0))
    {
      LOG(D4) << "cdb after sg.dxfer_len - sg.resid != sizeof(CScsiCmdInquiry_StandardData || resp->m_PeripheralDeviceType != 0x0";
      IFLOG(D4) DtaHexDump(cdb, sizeof (cdb));
      LOG(D4) << "sense after ";
      IFLOG(D4) DtaHexDump(sense, sizeof (sense));
      disk_info->devType = DEVICE_TYPE_OTHER;
      LOG(D4) << "sg.dxfer_len=" << sg.dxfer_len << " sg.resid=" << sg.resid <<
        " sizeof(CScsiCmdInquiry_StandardData)=" << sizeof(CScsiCmdInquiry_StandardData) <<
        " resp->m_PeripheralDeviceType=" << resp->m_PeripheralDeviceType;
      free(buffer);
      return;
    }

  // fill out disk info fields
  safecopy(disk_info->serialNum, sizeof(disk_info->serialNum), resp->m_T10VendorId, sizeof(resp->m_T10VendorId));
  safecopy(disk_info->firmwareRev, sizeof(disk_info->firmwareRev), resp->m_ProductRevisionLevel, sizeof(resp->m_ProductRevisionLevel));
  safecopy(disk_info->modelNum, sizeof(disk_info->modelNum), resp->m_ProductId, sizeof(resp->m_ProductId));

  // device is apparently a SCSI disk
  disk_info->devType = DEVICE_TYPE_SAS;
  isSAS = 1;

  // free buffer and return
  free(buffer);
  return;
}
/** Close the device reference so this object can be delete. */
DtaDevLinuxSata::~DtaDevLinuxSata()
{
  LOG(D1) << "Destroying DtaDevLinuxSata";
  close(fd);
}

#endif // NO_LONGER_NEEDED
