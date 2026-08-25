#ifndef ADRBUBBLEBOOTER_ADRENALINE_COMPAT_H
#define ADRBUBBLEBOOTER_ADRENALINE_COMPAT_H

#include <stdint.h>

/*
 * On-disk data/boot.bin layout used by AdrBubbleBooter VPK Edition v1.3.
 * The offsets and 0x140-byte size are corroborated by all three runtime
 * modules and by the surviving modified Adrenaline source.
 */
typedef struct BootInfo {
	int32_t magic;          /* 0x00: "ABB\0" when initialized. */
	int32_t driver;         /* 0x04: raw PSP ISO-driver selector. */
	int32_t execute;        /* 0x08: ISO executable selector. */
	int32_t customized;     /* 0x0C: global or per-bubble settings. */
	int32_t loadstate;      /* 0x10: zero or one-based state slot. */
	int32_t psbutton;       /* 0x14: PS-button behavior. */
	int32_t suspend;        /* 0x18: thread-suspension behavior. */
	int32_t cpuspeed;       /* 0x1C: PSP CPU-speed selector. */
	int32_t plugins;        /* 0x20: plugin policy. */
	int32_t nonpdrm;        /* 0x24: NoDRM policy. */
	int32_t highmemory;     /* 0x28: high-memory policy. */
	int32_t reserved[5];    /* 0x2C..0x3F: preserved unknown words. */
	char    file_path[256]; /* 0x40: selected PSP content path. */
} BootInfo;

_Static_assert(sizeof(BootInfo) == 0x140, "BootInfo must match boot.bin");
_Static_assert(__builtin_offsetof(BootInfo, file_path) == 0x40,
	"BootInfo.file_path offset must match boot.bin");

#define BOOT_INFO_MAGIC 0x00424241

#endif
