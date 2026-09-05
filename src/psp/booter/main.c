#include <pspkernel.h>
#include <pspsdk.h>
#include <pspextratypes.h>

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "../../common/adrenaline_compat.h"
#include "imports.h"

PSP_MODULE_INFO("Booter", PSP_MODULE_KERNEL, 1, 0);

#define NOINLINE __attribute__((noinline))

enum ContentType {
	CONTENT_UNKNOWN   = 0,
	CONTENT_ISO       = 1,
	CONTENT_PSP_PBP   = 2,
	CONTENT_NPDRM_PBP = 3,
	CONTENT_PS1_PBP   = 4,
};

/*
 * These are the raw indices consumed by the SystemCtrl binary paired with the
 * reference booter. They intentionally do not use a newer systemctrl.h enum.
 */
enum BootConfigIndex {
#if ADRBUBBLE_ISAGE_CONFIG
	/* SEUmdModes in Isage's pinned psp-cfw-sdk, not ISO menu indices. */
	BOOT_CONFIG_MARCH33 = 2,
	BOOT_CONFIG_NP9660  = 3,
	BOOT_CONFIG_INFERNO = 4,
#else
	BOOT_CONFIG_MARCH33 = 1,
	BOOT_CONFIG_NP9660  = 2,
	BOOT_CONFIG_INFERNO = 3,
#endif
};

enum BubbleDriver {
	BUBBLE_DRIVER_INFERNO = 0,
	BUBBLE_DRIVER_MARCH33 = 1,
	BUBBLE_DRIVER_NP9660  = 2,
};

enum BubbleExecute {
	BUBBLE_EXECUTE_EBOOT_BIN = 0,
	BUBBLE_EXECUTE_EBOOT_OLD = 1,
	BUBBLE_EXECUTE_BOOT_BIN  = 2,
};

enum {
	PSP_INIT_APITYPE_UMD         = 0x120,
	PSP_INIT_APITYPE_UMD_EMU_MS1 = 0x123,
	PSP_INIT_APITYPE_MS2         = 0x141,
	PSP_INIT_APITYPE_MS5         = 0x144,
};

_Static_assert(sizeof(BootInfo) == 0x140,
	"PSP booter boot-info layout must match the reference PRX");

/*
 * The reference BSS contains one unreferenced word before BootInfo. Its
 * meaning cannot be recovered from the binary, so keep the storage without
 * assigning it invented semantics.
 */
static uint32_t reference_bss_word __attribute__((used)); /* Unreferenced 4-byte slot. */
static BootInfo boot_info;                                /* Raw data/boot.bin image. */
static char     ps1_title_id[12];                         /* Nine-byte PS1 disc ID plus padding. */

NOINLINE int booter_thread(SceSize args, void *argp);

static NOINLINE __attribute__((used)) int reference_entry_prefix(void) {
	return 0;
}

int module_start(SceSize args, void *argp) {
	SceUID thread = sceKernelCreateThread(
		"BooterThread",
		booter_thread,
		0x10,
		0x1800,
		0,
		NULL
	);
	if (thread >= 0)
		sceKernelStartThread(thread, args, argp);
	return 0;
}

NOINLINE int launch_content(int type) {
	unsigned int             old_k1 = pspSdkSetK1(0); /* Enter kernel-addressing context. */
	SceKernelLoadExecVSHParam param;
	int                       apitype = 0;

	memset(&param, 0, sizeof(param));
	param.size = sizeof(param);

	if (type == CONTENT_NPDRM_PBP) {
		SetUmdFile(""); /* NPDRM still enters the UMD-emulation runlevel. */
		sctrlSESetBootConfFileIndex(BOOT_CONFIG_NP9660);
		param.argp = "disc0:/PSP_GAME/SYSDIR/EBOOT.BIN";
		param.key = "umdemu";
		apitype = PSP_INIT_APITYPE_UMD_EMU_MS1;
	} else if (type == CONTENT_ISO) {
		SetUmdFile(boot_info.file_path); /* SystemCtrl consumes this exact path. */

		if (boot_info.driver == BUBBLE_DRIVER_INFERNO) {
			sctrlSESetBootConfFileIndex(BOOT_CONFIG_INFERNO);
		} else if (boot_info.driver == BUBBLE_DRIVER_MARCH33) {
			sctrlSESetBootConfFileIndex(BOOT_CONFIG_MARCH33);
		} else if (boot_info.driver == BUBBLE_DRIVER_NP9660) {
			sctrlSESetBootConfFileIndex(BOOT_CONFIG_NP9660);
		}

		sctrlSESetDiscType(ISO_DISC_TYPE_GAME);
		sctrlSEMountUmdFromFile(boot_info.file_path, 1, 1);

		if (boot_info.execute == BUBBLE_EXECUTE_EBOOT_OLD) {
			param.argp = "disc0:/PSP_GAME/SYSDIR/EBOOT.OLD";
		} else if (boot_info.execute == BUBBLE_EXECUTE_BOOT_BIN) {
			param.argp = "disc0:/PSP_GAME/SYSDIR/BOOT.BIN";
		} else {
			param.argp = "disc0:/PSP_GAME/SYSDIR/EBOOT.BIN";
		}

		param.key = "umdemu";
		apitype = PSP_INIT_APITYPE_UMD;
	} else if (type == CONTENT_PSP_PBP) {
		param.argp = boot_info.file_path;
		param.key = "game";
		apitype = PSP_INIT_APITYPE_MS2;
	} else if (type == CONTENT_PS1_PBP) {
		param.argp = boot_info.file_path;
		param.key = "pops";
		apitype = PSP_INIT_APITYPE_MS5;
		sceKernelSetParamSfo(
			ps1_title_id,
			1,
			0,
			"00.00",
			1,
			0,
			"6.60"
		);
	}

	param.args = strlen(param.argp) + 1; /* LoadExec expects the terminating NUL. */
	pspSdkSetK1(old_k1);                 /* Restore the caller's K1 value. */

	const char *file = type == CONTENT_ISO
		? (const char *)param.argp
		: boot_info.file_path;
	return sctrlKernelLoadExecVSHWithApitype(apitype, file, &param);
}

NOINLINE int read_file(const char *path, void *buffer, int size) {
	SceUID fd = sceIoOpen(path, PSP_O_RDONLY, 0);
	if (fd >= 0) {
		int result = sceIoRead(fd, buffer, size);
		sceIoClose(fd);
		fd = result;
	}
	return fd;
}

NOINLINE char *path_after_pspemu_device(char *path) {
	char *colon = strrchr(path, ':');
	if (colon != NULL)
		path = colon + 7; /* Skip ":pspemu" and retain the following slash. */
	return path;
}

NOINLINE int check_file(const char *path) {
	SceIoStat stat;
	memset(&stat, 0, sizeof(stat));
	return sceIoGetstat(path, &stat);
}

NOINLINE void flush_caches(void) {
	sceKernelDcacheWritebackAll();
	sceKernelIcacheClearAll();
}

NOINLINE int detect_content_type(const char *path) {
	PBPHeader pbp_header;
	char      header[16];
	SceUID    fd = sceIoOpen(path, PSP_O_RDONLY, 0);
	int       type = fd; /* Preserve a negative open error as the result. */

	if (fd >= 0) {
		sceIoRead(fd, &pbp_header, sizeof(pbp_header)); /* Read the PBP offset table. */
		sceIoLseek(fd, 0, PSP_SEEK_SET);
		sceIoRead(fd, header, sizeof(header));

		if (memcmp(header, "\0PBP", 4) != 0) {
			type = CONTENT_ISO;
		} else {
			sceIoLseek(fd, pbp_header.psar_offset, PSP_SEEK_SET); /* Inspect DATA.PSAR. */
			sceIoRead(fd, header, sizeof(header));

			if (memcmp(header, "PSISOIMG0000", 12) == 0
					|| memcmp(header, "PSTITLEIMG000000", 16) == 0) {
				sceIoLseek(fd, 0x130, PSP_SEEK_SET);
				sceIoRead(fd, ps1_title_id, 9); /* Reference reads no explicit terminator. */
				type = CONTENT_PS1_PBP;
			} else if (memcmp(header, "NPUMDIMG", 8) == 0) {
				type = CONTENT_NPDRM_PBP;
			} else {
				type = CONTENT_PSP_PBP;
			}
		}

		sceIoClose(fd);
		flush_caches();
	}

	return type;
}

NOINLINE int booter_thread(SceSize args, void *argp) {
	(void)args;
	(void)argp;
	BootInfo *boot_info_ptr = &boot_info; /* Kept distinct for reference register allocation. */

	/*
	 * This empty compiler barrier has no runtime effect. It preserves the
	 * full BootInfo address in the same saved register form as the reference
	 * GCC output instead of retaining only its high half.
	 */
	__asm__ volatile ("" : "+r"(boot_info_ptr));

	memset(boot_info_ptr, 0, sizeof(boot_info));
	int result = read_file(
		"ms0:/__APPID__/data/boot.bin",
		boot_info_ptr,
		sizeof(boot_info)
	);
	if (result >= 0) {
		char path[256]; /* Temporary ms0:-relative path reconstructed in place. */
		sprintf(path, "ms0:%s", path_after_pspemu_device(boot_info.file_path));
		strncpy(boot_info.file_path, path, sizeof(boot_info.file_path) - 1);

		result = check_file(boot_info.file_path);
		if (result >= 0) {
			int type = detect_content_type(boot_info.file_path);
			if (type != CONTENT_UNKNOWN) {
				/* The reference falls through with this call's value in v0. */
				launch_content(type);
			} else {
				return -1;
			}
		} else {
			return -1;
		}
	} else {
		return -1;
	}
} /* The reference intentionally has no explicit success return. */
