/*
 * PSP Software Development Kit - http://www.pspdev.org
 * -----------------------------------------------------------------------
 * Licensed under the BSD license, see LICENSE in PSPSDK root for details.
 *
 * Compatibility subset of the 2016 PSPSDK pspmoduleinfo.h. The inline
 * boundary sections are loader-visible and are required by the reference
 * booter; current PSPSDK emits them through a separate archive instead.
 */
#ifndef PSPMODULEINFO_H
#define PSPMODULEINFO_H

typedef struct _scemoduleinfo {
	unsigned short modattribute;  /* 0x00: module attribute flags. */
	unsigned char  modversion[2]; /* 0x02: minor, then major version. */
	char           modname[27];   /* 0x04: fixed-size module name. */
	char           terminal;      /* 0x1F: explicit name terminator. */
	void          *gp_value;      /* 0x20: module global pointer. */
	void          *ent_top;       /* 0x24: export table start. */
	void          *ent_end;       /* 0x28: export table end. */
	void          *stub_top;      /* 0x2C: import table start. */
	void          *stub_end;      /* 0x30: import table end. */
} _sceModuleInfo;

typedef const _sceModuleInfo SceModuleInfo;

extern char _gp[];

enum PspModuleInfoAttr {
	PSP_MODULE_USER         = 0,
	PSP_MODULE_NO_STOP      = 0x0001,
	PSP_MODULE_SINGLE_LOAD  = 0x0002,
	PSP_MODULE_SINGLE_START = 0x0004,
	PSP_MODULE_KERNEL       = 0x1000,
};

#define PSP_MODULE_INFO(name, attributes, major_version, minor_version) \
	__asm__ (                                                       \
	"    .set push\n"                                               \
	"    .section .lib.ent.top, \"a\", @progbits\n"                 \
	"    .align 2\n"                                                \
	"    .word 0\n"                                                 \
	"__lib_ent_top:\n"                                              \
	"    .section .lib.ent.btm, \"a\", @progbits\n"                 \
	"    .align 2\n"                                                \
	"__lib_ent_bottom:\n"                                           \
	"    .word 0\n"                                                 \
	"    .section .lib.stub.top, \"a\", @progbits\n"                \
	"    .align 2\n"                                                \
	"    .word 0\n"                                                 \
	"__lib_stub_top:\n"                                             \
	"    .section .lib.stub.btm, \"a\", @progbits\n"                \
	"    .align 2\n"                                                \
	"__lib_stub_bottom:\n"                                          \
	"    .word 0\n"                                                 \
	"    .set pop\n"                                                \
	"    .text\n"                                                  \
	);                                                              \
	extern char __lib_ent_top[], __lib_ent_bottom[];                \
	extern char __lib_stub_top[], __lib_stub_bottom[];              \
	SceModuleInfo module_info                                       \
		__attribute__((section(".rodata.sceModuleInfo"),        \
			       aligned(16), unused)) = {                \
	  attributes, { minor_version, major_version }, name, 0, _gp,  \
	  __lib_ent_top, __lib_ent_bottom,                              \
	  __lib_stub_top, __lib_stub_bottom                             \
	}

#endif
