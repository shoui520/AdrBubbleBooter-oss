set(PDCLIB "${ADRBUBBLE_LIBK_SOURCE}/thirdparty/pdclib")
set(BOOTCONV_RUNTIME_SOURCES
  ${PDCLIB}/functions/stdio/snprintf.c
  ${PDCLIB}/functions/stdio/sprintf.c
  ${PDCLIB}/functions/stdio/vsnprintf.c
  ${PDCLIB}/functions/string/memset.c
  ${PDCLIB}/functions/string/strchr.c
  ${PDCLIB}/functions/string/strcmp.c
  ${PDCLIB}/functions/string/strcpy.c
  ${PDCLIB}/functions/string/strlen.c
  ${PDCLIB}/functions/string/strrchr.c
  ../common/libk_errno.c
  ${PDCLIB}/functions/_PDCLIB/digits.c
  ${PDCLIB}/functions/_PDCLIB/print.c
  ${PDCLIB}/functions/stdlib/abs.c
  ${PDCLIB}/functions/stdlib/strtol.c
  ${PDCLIB}/functions/_PDCLIB/strtox_main.c
  ${PDCLIB}/functions/_PDCLIB/strtox_prelim.c
  ${PDCLIB}/functions/ctype/isspace.c
  ${PDCLIB}/functions/ctype/tolower.c
  ${PDCLIB}/functions/string/memchr.c
)

add_executable(bootconv
  main.c
  ${BOOTCONV_RUNTIME_SOURCES}
)

target_compile_options(bootconv PRIVATE
  -Os
  -Wall
  -Wextra
)
set_source_files_properties(main.c PROPERTIES COMPILE_OPTIONS
  "-fno-builtin;-fno-toplevel-reorder;-mword-relocations"
)
set_source_files_properties(${BOOTCONV_RUNTIME_SOURCES} PROPERTIES
  COMPILE_OPTIONS
    "-Werror;-pedantic;-std=c99;-ffreestanding;-I${PDCLIB}/includes;-I${PDCLIB}/internals;-I${ADRBUBBLE_LIBK_SOURCE}/include"
)
target_link_options(bootconv PRIVATE
  -nostdlib
  -Wl,-q
)
target_link_libraries(bootconv
  gcc
  c
  taihen_stub
  SceAppMgr_stub
  SceKernelThreadMgr_stub
  SceIofilemgr_stub
  SceLibKernel_stub
)

adrbubble_create_self(bootconv.suprx bootconv 0x147042CF
  CONFIG ${CMAKE_CURRENT_SOURCE_DIR}/exports.yml
  MAKE_FSELF ${ADRBUBBLE_LEGACY_MAKE_FSELF}
  VELF_NORMALIZER ${CMAKE_SOURCE_DIR}/tools/normalize_closed_vita_velf.py
  UNSAFE
)
