set(VITA_APP_NAME "ebooter")
set(VITA_TITLEID "PSPEMUCFW")

add_executable(ebooter
  main.c
  graphics.c
  font.c
)

target_compile_options(ebooter PRIVATE
  -Wall
  -O3
)

target_link_options(ebooter PRIVATE
  -Wl,-q
)

target_link_libraries(ebooter
  taihen_stub
  SceAppMgr_stub
  SceDisplay_stub
  SceSysmodule_stub
)

adrbubble_create_self(per-bubble-eboot.bin ebooter 0x83317876
  AUTHID 0x2800000000000001
  CONFIG ${CMAKE_CURRENT_SOURCE_DIR}/exports.yml
  MAKE_FSELF ${ADRBUBBLE_LEGACY_MAKE_FSELF}
  VELF_NORMALIZER ${CMAKE_SOURCE_DIR}/tools/normalize_vita_ebooter_velf.py
  UNSAFE
)
