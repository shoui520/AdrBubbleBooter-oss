	.set noreorder

#include "pspimport.s"

IMPORT_START "SysMemForKernel",     0x00010011
IMPORT_FUNC  "SysMemForKernel",     0xF91FE6AA, sceKernelSetParamSfo

IMPORT_START "SystemCtrlForKernel", 0x00090000
IMPORT_FUNC  "SystemCtrlForKernel", 0x2D10FB28, sctrlKernelLoadExecVSHWithApitype
IMPORT_FUNC  "SystemCtrlForKernel", 0x85B520C6, sctrlSEMountUmdFromFile
IMPORT_FUNC  "SystemCtrlForKernel", 0x31C6160D, sctrlSESetDiscType
IMPORT_FUNC  "SystemCtrlForKernel", 0xB64186D0, SetUmdFile
IMPORT_FUNC  "SystemCtrlForKernel", 0x5CB025F0, sctrlSESetBootConfFileIndex

IMPORT_START "LoadCoreForKernel",   0x00010000
IMPORT_FUNC  "LoadCoreForKernel",   0xD8779AC6, sceKernelIcacheClearAll

IMPORT_START "IoFileMgrForKernel",  0x00010000
IMPORT_FUNC  "IoFileMgrForKernel",  0x810C4BC3, sceIoClose
IMPORT_FUNC  "IoFileMgrForKernel",  0x109F50BC, sceIoOpen
IMPORT_FUNC  "IoFileMgrForKernel",  0x6A638D83, sceIoRead
IMPORT_FUNC  "IoFileMgrForKernel",  0x27EB27B8, sceIoLseek
IMPORT_FUNC  "IoFileMgrForKernel",  0xACE946E8, sceIoGetstat

IMPORT_START "UtilsForKernel",      0x00090000
IMPORT_FUNC  "UtilsForKernel",      0x79D1C3FA, sceKernelDcacheWritebackAll

IMPORT_START "ThreadManForKernel",  0x00010000
IMPORT_FUNC  "ThreadManForKernel",  0x446D8DE6, sceKernelCreateThread
IMPORT_FUNC  "ThreadManForKernel",  0xF475845D, sceKernelStartThread

IMPORT_START "SysclibForKernel",    0x00010000
IMPORT_FUNC  "SysclibForKernel",    0x4C0E0274, strrchr
IMPORT_FUNC  "SysclibForKernel",    0xB49A7697, strncpy
IMPORT_FUNC  "SysclibForKernel",    0x52DF196C, strlen
IMPORT_FUNC  "SysclibForKernel",    0x10F3BB61, memset
IMPORT_FUNC  "SysclibForKernel",    0x81D0D1F7, memcmp
IMPORT_FUNC  "SysclibForKernel",    0x7661E728, sprintf
