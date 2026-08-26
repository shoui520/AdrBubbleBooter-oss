TARGET = booter
OBJS = main.o imports.o k1set.o empty_sections.o

PSPDEV ?= $(error PSPDEV is undefined)
PSPSDK ?= $(PSPDEV)/psp/sdk
PSP_CC ?= $(PSPDEV)/bin/psp-gcc
PSP_LD ?= $(PSPDEV)/bin/psp-ld
PSP_LAYOUT_LD ?= $(PSP_LD)
PSP_FIXUP ?= $(PSPDEV)/bin/psp-fixup-imports
PSP_PRXGEN ?= $(PSPDEV)/bin/psp-prxgen
PSP_GCC_TOOL_DIR ?= $(PSPDEV)/psp/bin
PSP_HEADER_COMPAT_FLAGS ?=
PYTHON ?= python3
PSP_NORMALIZE ?= ../../../tools/normalize_psp_booter.py

CPPFLAGS = \
	-Icompat \
	-I../.. \
	-I$(PSPDEV)/psp/include \
	-I$(PSPSDK)/include \
	-D_PSP_FW_VERSION=600 \
	$(ADRBUBBLE_PSP_CPPFLAGS) \
	$(PSP_HEADER_COMPAT_FLAGS)
CFLAGS = \
	-B$(PSP_GCC_TOOL_DIR)/ \
	-O2 -Os -G0 -Wall -Wextra \
	-fno-pic -fno-builtin -fno-toplevel-reorder -fno-gcse \
	-mno-check-zero-division
ASFLAGS = $(CFLAGS)
LDFLAGS = -q -T$(PSPSDK)/lib/linkfile.prx

.PHONY: all clean

all: $(TARGET).prx

$(TARGET).elf: $(OBJS)
	$(PSP_LAYOUT_LD) $(LDFLAGS) $^ -o $@
	$(PSP_FIXUP) $@

$(TARGET).prx: $(TARGET).elf $(PSP_NORMALIZE)
	$(PSP_PRXGEN) $< $@
	$(PYTHON) $(PSP_NORMALIZE) $@

%.o: %.c
	$(PSP_CC) $(CPPFLAGS) $(CFLAGS) -c $< -o $@

%.o: %.S
	$(PSP_CC) $(CPPFLAGS) $(ASFLAGS) -c $< -o $@

clean:
	rm -f $(TARGET).prx $(TARGET).elf $(OBJS)
