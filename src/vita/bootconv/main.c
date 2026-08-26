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

static char device_name[256]; /* Scratch copy used to isolate the device prefix. */
static char ini_value[256];   /* Last matching boot.inf value. */
/* PDCLib's module-local errno object occupies this exact BSS slot. */
int _PDCLIB_errno __attribute__((used)) = 0;
static unsigned char adrenaline_config[0xB8]; /* Host AdrenalineConfig bytes. */
static BootInfo      boot_info;                /* Generated 0x140-byte boot record. */

int   check_file(const char *path);
int   get_file_size(const char *path);
int   read_file(const char *path, void *buffer, int size);
int   write_file(const char *path, const void *buffer, int size);
char *get_device_name(const char *path);
char *path_after_pspemu_device(char *path);
char *after_last_colon(char *path);
int   starts_with(const char *text, const char *prefix);
char *after_first_equals(char *line);
char *read_ini_value(const char *path, const char *key);

const char *get_device_prefix(int location) {
	switch (location) {
		case 1:
			return "ur0:";
		case 2:
			return "imc0:";
		case 3:
			return "xmc0:";
		case 4:
			return "uma0:";
		default:
			return "ux0:";
	}
}

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

	char app_title_id[12]; /* Current Vita title ID. */
	sceAppMgrGetNameById(sceKernelGetProcessId(), app_title_id);
	if (strcmp(app_title_id, ADRENALINE_TITLE_ID) == 0)
		return 0;

	memset(adrenaline_config, 0, sizeof(adrenaline_config));
	read_file(
		"ux0:app/" ADRENALINE_TITLE_ID "/adrenaline.bin",
		adrenaline_config,
		sizeof(adrenaline_config)
	);

	char boot_bin_path[64]; /* Destination data/boot.bin path. */
	char boot_inf_path[64]; /* Legacy data/boot.inf path. */
	sprintf(boot_bin_path, "ux0:app/%s/data/boot.bin", app_title_id);
	snprintf(
		boot_inf_path,
		sizeof(boot_inf_path),
		"ux0:app/%s/data/boot.inf",
		app_title_id
	);

	if (check_file(boot_inf_path) >= 0 && check_file(boot_bin_path) < 0) {
#if ADRBUBBLE_ISAGE_CONFIG
		const char *prefix = get_device_prefix(adrenaline_config[0x0B]);
#else
		const char *prefix = get_device_prefix(
			*(int32_t *)(adrenaline_config + 0x18) /* AdrenalineConfig.ms_location. */
		);
#endif
		char *legacy_path = read_ini_value(boot_inf_path, "PATH");
		snprintf(
			boot_info.file_path,
			sizeof(boot_info.file_path),
			"%spspemu%s",
			prefix,
			after_last_colon(legacy_path)
		);
		if (check_file(boot_info.file_path) < 0)
			return sceKernelExitProcess(0);

		boot_info.magic = BOOT_INFO_MAGIC; /* Mark the converted record as ABB format. */
		write_file(boot_bin_path, &boot_info, sizeof(boot_info));
		sceIoRemove(boot_inf_path); /* Conversion is one-shot after boot.bin is written. */
	}

	return 0;
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

char *path_after_pspemu_device(char *path) {
	char *result = path;
	char *colon = strrchr(path, ':');
	if (colon != NULL)
		result = colon + 7; /* Skip ":pspemu" and retain the following slash. */
	return result;
}

char *after_last_colon(char *path) {
	return strrchr(path, ':') + 1; /* boot.inf PATH is device-qualified. */
}

int starts_with(const char *text, const char *prefix) {
	return strncasecmp(text, prefix, strlen(prefix)) == 0;
}

char *after_first_equals(char *line) {
	return strchr(line, '=') + 1; /* Matching lines are expected to contain '='. */
}

char *read_ini_value(const char *path, const char *key) {
	SceUID fd = sceIoOpen(path, SCE_O_RDONLY, 0);
	if (fd < 0) {
		sceIoClose(fd); /* Preserve the closed module's invalid-handle close. */
		return NULL;
	}

	char data[1024]; /* The original parser examines at most one KiB. */
	memset(data, 0, sizeof(data));
	sceIoRead(fd, data, sizeof(data));
	sceIoClose(fd);

	char *save = NULL;
	char *line = strtok_r(data, "\r\n", &save);
	while (line != NULL) {
		if (line[0] != '\0' && line[0] != '#' && starts_with(line, key))
			snprintf(ini_value, sizeof(ini_value), "%s", after_first_equals(line)); /* Last match wins. */
		line = strtok_r(NULL, "\r\n", &save);
	}
	return ini_value;
}
