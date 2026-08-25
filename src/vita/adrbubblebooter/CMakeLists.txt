set(PDCLIB "${ADRBUBBLE_LIBK_SOURCE}/thirdparty/pdclib")
set(ADRBUBBLE_RUNTIME_SOURCES
  ${PDCLIB}/functions/stdio/sprintf.c
  ${PDCLIB}/functions/stdio/vsnprintf.c
  ${PDCLIB}/functions/string/memset.c
  ${PDCLIB}/functions/string/strcpy.c
  ${PDCLIB}/functions/string/strlen.c
  ${PDCLIB}/functions/string/strncpy.c
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

add_executable(adrbubblebooter
  main.c
  ${ADRBUBBLE_RUNTIME_SOURCES}
)

target_compile_options(adrbubblebooter PRIVATE
  -Os
  -Wall
  -Wextra
)
set_source_files_properties(main.c PROPERTIES COMPILE_OPTIONS
  "-fno-builtin;-fno-toplevel-reorder;-mword-relocations"
)
set_source_files_properties(${ADRBUBBLE_RUNTIME_SOURCES} PROPERTIES
  COMPILE_OPTIONS
    "-Werror;-pedantic;-std=c99;-ffreestanding;-I${PDCLIB}/includes;-I${PDCLIB}/internals;-I${ADRBUBBLE_LIBK_SOURCE}/include"
)
target_link_options(adrbubblebooter PRIVATE
  -nostdlib
  -Wl,-q
)
target_link_libraries(adrbubblebooter
  gcc
  c
  taihen_stub
  SceAppMgr_stub
  SceKernelThreadMgr_stub
  SceIofilemgr_stub
  SceLibKernel_stub
)

adrbubble_create_self(adrbubblebooter.suprx adrbubblebooter 0xBF7F98B3
  CONFIG ${CMAKE_CURRENT_SOURCE_DIR}/exports.yml
  ELF_CREATE ${ADRBUBBLE_ADR_ELF_CREATE}
  MAKE_FSELF ${ADRBUBBLE_LEGACY_MAKE_FSELF}
  VELF_NORMALIZER ${CMAKE_SOURCE_DIR}/tools/normalize_closed_vita_velf.py
  UNSAFE
)
