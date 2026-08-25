TARGET = libvitashaders.a

# This is the exact .rodata/member order in the tested adrenaline_user module.
# In particular, the Simple programs are vertex then fragment; reversing their
# filenames creates an invalid SceGxm shader pair at runtime.
PROGRAMS = \
	advanced_aa_f \
	advanced_aa_v \
	lcd3x_f \
	lcd3x_v \
	opaque_v \
	sharp_bilinear_f \
	sharp_bilinear_v \
	texture_f \
	sharp_bilinear_simple_v \
	sharp_bilinear_simple_f

OBJECTS = $(addprefix build/obj/,$(addsuffix .o,$(PROGRAMS)))

CC = arm-vita-eabi-gcc
AR = arm-vita-eabi-ar
PYTHON ?= python3
PSP2_SDK_BIN ?=

.PHONY: all clean verify-gxp verify-archive

all: $(TARGET)

verify-gxp:
	$(PYTHON) build_gxp.py --sdk-bin "$(PSP2_SDK_BIN)" --out-dir build/gxp --reference-dir gxp

$(TARGET): $(OBJECTS)
	@set -eu; \
	archive_dir=$$(mktemp -d build/archive.XXXXXX); \
	$(AR) rcsD "$$archive_dir/$(TARGET)" $^; \
	mv "$$archive_dir/$(TARGET)" $@; \
	rmdir "$$archive_dir"

build/generated/%.c: gxp/%.gxp gxp_to_c.py
	@mkdir -p $(@D)
	$(PYTHON) gxp_to_c.py $< $@

build/obj/%.o: build/generated/%.c
	@mkdir -p $(@D)
	$(CC) -Wall -O3 -ftree-vectorize -mfloat-abi=hard -ffast-math \
		-fsingle-precision-constant -funroll-loops -fno-lto -c $< -o $@

verify-archive: $(TARGET)
	$(PYTHON) verify_archive.py $(TARGET) --gxp-dir gxp \
		--prefix $(CC:-gcc=)

clean:
	rm -rf $(TARGET) build
