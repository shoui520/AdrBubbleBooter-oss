/*
	Adrenaline
	Copyright (C) 2016-2017, TheFloW
	Modified for AdrBubbleBooter by LMAN

	This program is free software: you can redistribute it and/or modify
	it under the terms of the GNU General Public License as published by
	the Free Software Foundation, either version 3 of the License, or
	(at your option) any later version.

	This program is distributed in the hope that it will be useful,
	but WITHOUT ANY WARRANTY; without even the implied warranty of
	MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
	GNU General Public License for more details.

	You should have received a copy of the GNU General Public License
	along with this program.  If not, see <http://www.gnu.org/licenses/>.
*/

#include <psp2/appmgr.h>
#include <psp2/io/devctl.h>
#include <psp2/io/dirent.h>
#include <psp2/io/stat.h>
#include <psp2/kernel/processmgr.h>
#include <taihen.h>
#include <string.h>
#include "graphics.h"

#define printf psvDebugScreenPrintf

int main() {

	int res; /* Preserve the kernel-module loader result. */

	psvDebugScreenInit();

	// Safe mode
	if (sceIoDevctl("ux0:", 0x3001, NULL, 0, NULL, 0) == 0x80010030) {
		printf("Please enable unsafe homebrew first before using this software.");
		while (1); /* Fatal prerequisite failure. */
	}

	// Check for Adrenaline files
	SceIoStat stat;
	memset(&stat, 0, sizeof(SceIoStat));
	if (sceIoGetstat("ux0:app/PSPEMUCFW/eboot.bin", &stat) < 0 &&
	    sceIoGetstat("ux0:app/PSPEMUCFW/eboot.pbp", &stat) < 0) {
		printf("Adrenaline has not been installed yet.\r\n\n");
		printf("In order to use AdrBubbleBooter you need to install Adrenaline first.");
		while (1); /* Adrenaline must be installed before bubble launch. */
	}

	// Load kernel module
	res = taiLoadStartKernelModule("ux0:app/PSPEMUCFW/sce_module/adrenaline_kernel.skprx", 0, NULL, 0); /* Start the host bridge. */
	if (res < 0) {
		printf("Could not load adrenaline_kernel.skprx. Please reboot or use the AdrBubbleBooterInstaller.");
		while (1); /* Kernel bridge failure cannot be recovered here. */
	}

	return 0;

}
