#include <psp2/appmgr.h>
#include <psp2/io/fcntl.h>
#include <psp2/io/stat.h>
#include <psp2/kernel/processmgr.h>
#include <taihen.h>

#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <strings.h>

#include "../../common/adrenaline_compat.h"

/* Present in the later VitaSDK public header with this exact ABI and NID. */
int sceAppMgrGetNameById(SceUID pid, char *name);

#define ADRENALINE_TITLE_ID "PSPEMUCFW"
#define CONFIG_FALLBACK_SIZE 0x60

typedef struct LegacyBootInfo {
	int32_t fields[8];      /* 0x00..0x1F: legacy scalar settings. */
	char    file_path[256]; /* 0x20: legacy selected-content path. */
} LegacyBootInfo;

_Static_assert(sizeof(LegacyBootInfo) == 0x120,
	"legacy boot.bin layout must remain 0x120 bytes");

static char device_name[256]; /* Scratch copy used to isolate the device prefix. */
/* PDCLib's module-local errno object occupies this exact BSS slot. */
int _PDCLIB_errno __attribute__((used)) = 0;
static char           adrenaline_config_path[64];     /* Global Adrenaline settings path. */
static LegacyBootInfo legacy_boot_info;               /* Temporary 0x120-byte conversion input. */
static char           app_title_id[12];               /* Current Vita title ID. */
static char           bubble_config_path[64];         /* Per-bubble settings path. */
static unsigned char  config[CONFIG_FALLBACK_SIZE];   /* Global/per-bubble settings bytes. */
static BootInfo       boot_info;                      /* Current 0x140-byte boot record. */
static char           bubble_boot_path[64];           /* Current bubble's data/boot.bin path. */

int         check_file(const char *path);
int         get_file_size(const char *path);
int         read_file(const char *path, void *buffer, int size);
int         write_file(const char *path, const void *buffer, int size);
char       *after_last_colon(char *path);
char       *get_device_name(const char *path);
int         get_ms_location(const char *device);
const char *get_pspemu_root(int location);

int module_start(SceSize args, void *argp);
int module_stop(SceSize args, void *argp);
int _start(SceSize args, void *argp)
	__attribute__((weak, alias("module_start")));

int module_start(SceSize args, void *argp) {
	(void)args;
	(void)argp;

	tai_module_info_t tai_info;
	tai_info.size = sizeof(tai_info); /* taiHEN requires the caller-supplied size. */
	if (taiGetModuleInfo("ScePspemu", &tai_info) < 0)
		return sceKernelExitProcess(0);

	sceAppMgrGetNameById(sceKernelGetProcessId(), app_title_id); /* Identify direct vs bubble launch. */
	if (strcasecmp(app_title_id, ADRENALINE_TITLE_ID) == 0)
		return 0;

	sprintf(bubble_boot_path, "ux0:app/%s/data/boot.bin", app_title_id);
	sprintf(bubble_config_path, "ux0:app/%s/data/config.bin", app_title_id);
	strcpy(
		adrenaline_config_path,
		"ux0:app/" ADRENALINE_TITLE_ID "/adrenaline.bin"
	);

	if (check_file(bubble_boot_path) < 0)
		return sceKernelExitProcess(0);

	int boot_size = get_file_size(bubble_boot_path); /* Distinguish 0x120 and 0x140 layouts. */
	if (boot_size != sizeof(BootInfo)) {
		memset(&legacy_boot_info, 0, sizeof(legacy_boot_info));
		read_file(
			bubble_boot_path,
			&legacy_boot_info,
			sizeof(legacy_boot_info)
		);
		memset(&boot_info, 0, sizeof(boot_info));
		boot_info.magic      = legacy_boot_info.fields[0]; /* Legacy offset 0x00. */
		boot_info.driver     = legacy_boot_info.fields[1]; /* Legacy offset 0x04. */
		boot_info.execute    = legacy_boot_info.fields[2]; /* Legacy offset 0x08. */
		boot_info.customized = legacy_boot_info.fields[3]; /* Legacy offset 0x0C. */
		boot_info.loadstate  = legacy_boot_info.fields[4]; /* Legacy offset 0x10. */
		boot_info.psbutton   = legacy_boot_info.fields[5]; /* Legacy offset 0x14. */
		boot_info.suspend    = legacy_boot_info.fields[6]; /* Legacy offset 0x18. */
		strncpy(
			boot_info.file_path,
			legacy_boot_info.file_path,
			sizeof(boot_info.file_path)
		);
		write_file(
			bubble_boot_path,
			&boot_info,
			sizeof(boot_info)
		);
	} else {
		memset(&boot_info, 0, sizeof(boot_info));
		read_file(bubble_boot_path, &boot_info, boot_size);
	}

	int config_size = get_file_size(adrenaline_config_path); /* Preserve the host file's exact size. */
	if (config_size <= 0)
		config_size = CONFIG_FALLBACK_SIZE;
	memset(config, 0, config_size);
	read_file(adrenaline_config_path, config, config_size);
	if (boot_info.customized == 1)
		read_file(bubble_config_path, config, config_size);

	int location = get_ms_location(get_device_name(boot_info.file_path)); /* Map Vita device to pspemu root. */
	location &= ~(location >> 31); /* Clamp the reference's unknown-device -1 result to ux0. */

	char savestate_path[128];
	sprintf(
		savestate_path,
		"%s/PSP/SAVESTATE/STATE%02d.BIN",
		get_pspemu_root(location),
		(int)(boot_info.loadstate - 1)
	);
	if (boot_info.loadstate != 0 && check_file(savestate_path) >= 0)
		return 0;

	if (check_file(boot_info.file_path) >= 0) {
		*(int32_t *)(config + 0x18) = location; /* AdrenalineConfig.ms_location. */
		const char *output = boot_info.customized == 1
			? bubble_config_path
			: adrenaline_config_path;
		if (write_file(output, config, config_size) >= 0)
			return 0;
	}

	return sceKernelExitProcess(0);
}

int module_stop(SceSize args, void *argp) {
	(void)args;
	(void)argp;
	return 0;
}

int check_file(const char *path) {
	SceIoStat stat;
	memset(&stat, 0, sizeof(stat));
	return sceIoGetstat(path, &stat);
}

int get_file_size(const char *path) {
	SceUID fd = sceIoOpen(path, SCE_O_RDONLY, 0);
	if (fd < 0)
		return fd;

	int size = (int)sceIoLseek(fd, 0, SCE_SEEK_END); /* Reference returns the final seek position. */
	sceIoClose(fd);
	return size;
}

int read_file(const char *path, void *buffer, int size) {
	SceUID fd = sceIoOpen(path, SCE_O_RDONLY, 0);
	if (fd < 0)
		return fd;

	int read = sceIoRead(fd, buffer, size); /* Preserve the raw syscall result. */
	sceIoClose(fd);
	return read;
}

int write_file(const char *path, const void *buffer, int size) {
	SceUID fd = sceIoOpen(
		path,
		SCE_O_WRONLY | SCE_O_CREAT | SCE_O_TRUNC,
		0777
	);
	if (fd < 0)
		return fd;

	int written = sceIoWrite(fd, buffer, size); /* Preserve the raw syscall result. */
	sceIoClose(fd);
	return written;
}

char *after_last_colon(char *path) {
	return strrchr(path, ':') + 1; /* Callers provide a device-qualified path. */
}

char *get_device_name(const char *path) {
	if (strlen(path) <= sizeof(device_name)) {
		strcpy(device_name, path);
		char *colon = strrchr(device_name, ':'); /* Terminate immediately after the device name. */
		if (colon != NULL)
			*colon = '\0';
		return device_name;
	}
	return NULL;
}

int get_ms_location(const char *device) {
	if (strcasecmp(device, "ux0") == 0)
		return 0;
	if (strcasecmp(device, "ur0") == 0)
		return 1;
	if (strcasecmp(device, "imc0") == 0)
		return 2;
	if (strcasecmp(device, "xmc0") == 0)
		return 3;
	if (strcasecmp(device, "uma0") == 0)
		return 4;
	return -1;
}

const char *get_pspemu_root(int location) {
	switch (location) {
		case 1:
			return "ur0:pspemu";
		case 2:
			return "imc0:pspemu";
		case 3:
			return "xmc0:pspemu";
		case 4:
			return "uma0:pspemu";
		default:
			return "ux0:pspemu";
	}
}
