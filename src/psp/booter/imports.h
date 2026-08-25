#ifndef ADRBUBBLEBOOTER_PSP_BOOTER_IMPORTS_H
#define ADRBUBBLEBOOTER_PSP_BOOTER_IMPORTS_H

#include <pspiofilemgr.h>
#include <psploadexec_kernel.h>
#include <psptypes.h>

/* NID F91FE6AA from SysMemForKernel. */
int sceKernelSetParamSfo(
	const char *disc_id,
	int unknown1,
	int unknown2,
	const char *unknown3,
	int unknown4,
	int unknown5,
	const char *psp_version
);

/* Exact SystemCtrlForKernel ABI imported by the reference PRX. */
int sctrlKernelLoadExecVSHWithApitype(
	int apitype,
	const char *file,
	SceKernelLoadExecVSHParam *param
);
int  sctrlSEMountUmdFromFile(char *file, int noumd, int isofs); /* Mount selected ISO/CSO. */
void sctrlSESetDiscType(int type);                              /* Select the emulated disc type. */
void SetUmdFile(char *file);                                   /* Publish the active UMD path. */
void sctrlSESetBootConfFileIndex(int index);                    /* Select a PSP boot configuration. */

#endif
