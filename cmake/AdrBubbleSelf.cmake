include(CMakeParseArguments)

set(
  ADRBUBBLE_MAKE_FSELF
  "$ENV{VITASDK}/bin/vita-make-fself-fixed"
  CACHE FILEPATH
  "Pinned VitaSDK vita-make-fself with explicit module-NID support"
)
set(
  ADRBUBBLE_ELF_CREATE
  "${VITA_ELF_CREATE}"
  CACHE FILEPATH
  "Default pinned vita-elf-create used to construct module metadata"
)
set(
  ADRBUBBLE_LEGACY_MAKE_FSELF
  "${ADRBUBBLE_MAKE_FSELF}"
  CACHE FILEPATH
  "April 2017 vita-make-fself with explicit module-NID support"
)
set(
  ADRBUBBLE_LEGACY_MAKE_FSELF_SHA256
  "1d81600aa41663c4290d9486d59b9da4f372f02eba43010f1b9c9b668e6e0601"
  CACHE STRING
  "Locked identity of the tested patched April 2017 SELF packer"
)

if(NOT EXISTS "${ADRBUBBLE_MAKE_FSELF}")
  message(FATAL_ERROR
    "ADRBUBBLE_MAKE_FSELF does not exist: ${ADRBUBBLE_MAKE_FSELF}\n"
    "Build vita-toolchain 25d343b with the patch under toolchain/patches."
  )
endif()
if(NOT EXISTS "${ADRBUBBLE_LEGACY_MAKE_FSELF}")
  message(FATAL_ERROR
    "ADRBUBBLE_LEGACY_MAKE_FSELF does not exist: "
    "${ADRBUBBLE_LEGACY_MAKE_FSELF}"
  )
endif()
file(SHA256 "${ADRBUBBLE_LEGACY_MAKE_FSELF}" legacy_make_fself_sha256)
if(NOT "${legacy_make_fself_sha256}" STREQUAL
    "${ADRBUBBLE_LEGACY_MAKE_FSELF_SHA256}")
  message(FATAL_ERROR
    "Wrong April 2017 SELF packer identity: ${legacy_make_fself_sha256}"
  )
endif()

# This follows VitaSDK's vita_create_self macro while allowing each recovered
# module to select its evidenced packer/converter generation and exact auth ID.
# The optional VELF normalizer is a separate fail-closed provenance transform.
function(adrbubble_create_self target source module_nid)
  set(options UNCOMPRESSED UNSAFE)
  set(one_value_args AUTHID CONFIG ELF_CREATE MAKE_FSELF VELF_NORMALIZER)
  cmake_parse_arguments(adr_self "${options}" "${one_value_args}" "" ${ARGN})

  if(adr_self_ELF_CREATE)
    set(elf_create "${adr_self_ELF_CREATE}")
  else()
    set(elf_create "${ADRBUBBLE_ELF_CREATE}")
  endif()
  if(NOT EXISTS "${elf_create}")
    message(FATAL_ERROR "vita-elf-create does not exist: ${elf_create}")
  endif()

  if(adr_self_MAKE_FSELF)
    set(make_fself "${adr_self_MAKE_FSELF}")
  else()
    set(make_fself "${ADRBUBBLE_MAKE_FSELF}")
  endif()
  if(NOT EXISTS "${make_fself}")
    message(FATAL_ERROR "vita-make-fself does not exist: ${make_fself}")
  endif()

  set(elf_create_flags)
  set(elf_create_dependencies)
  if(adr_self_CONFIG)
    get_filename_component(config "${adr_self_CONFIG}" ABSOLUTE)
    list(APPEND elf_create_flags -e "${config}")
    list(APPEND elf_create_dependencies "${config}")
  endif()

  set(make_fself_flags -n "${module_nid}")
  if(NOT adr_self_UNCOMPRESSED)
    list(APPEND make_fself_flags -c)
  endif()
  if(NOT adr_self_UNSAFE)
    list(APPEND make_fself_flags -s)
  endif()
  if(adr_self_AUTHID)
    list(APPEND make_fself_flags -a "${adr_self_AUTHID}")
  endif()

  if(TARGET ${source})
    set(sourcepath "${CMAKE_CURRENT_BINARY_DIR}/${source}")
  else()
    set(sourcepath "${source}")
  endif()
  get_filename_component(sourcefile "${sourcepath}" NAME)

  if(adr_self_VELF_NORMALIZER)
    get_filename_component(
      velf_normalizer "${adr_self_VELF_NORMALIZER}" ABSOLUTE
    )
    if(NOT EXISTS "${velf_normalizer}")
      message(FATAL_ERROR "VELF normalizer does not exist: ${velf_normalizer}")
    endif()
    set(raw_velf "${CMAKE_CURRENT_BINARY_DIR}/${sourcefile}.raw.velf")
    set(velf "${CMAKE_CURRENT_BINARY_DIR}/${sourcefile}.velf")
  else()
    set(raw_velf "${CMAKE_CURRENT_BINARY_DIR}/${sourcefile}.velf")
    set(velf "${raw_velf}")
  endif()
  add_custom_command(
    OUTPUT "${raw_velf}"
    COMMAND "${elf_create}" ${elf_create_flags} "${sourcepath}" "${raw_velf}"
    DEPENDS "${sourcepath}" ${elf_create_dependencies}
    COMMENT "Converting to Sony ELF ${sourcefile}.raw.velf"
    VERBATIM
  )
  if(adr_self_VELF_NORMALIZER)
    add_custom_command(
      OUTPUT "${velf}"
      COMMAND "${velf_normalizer}" "${raw_velf}" "${velf}"
      DEPENDS "${raw_velf}" "${velf_normalizer}"
      COMMENT "Restoring evidenced VELF profile for ${sourcefile}"
      VERBATIM
    )
  endif()

  set(self_outfile "${CMAKE_CURRENT_BINARY_DIR}/${target}.out")
  add_custom_command(
    OUTPUT "${self_outfile}"
    COMMAND "${make_fself}" ${make_fself_flags} "${velf}" "${self_outfile}"
    DEPENDS "${velf}"
    COMMENT "Creating fixed-identity SELF ${target}"
    VERBATIM
  )

  add_custom_target(
    ${target} ALL
    DEPENDS "${self_outfile}"
    COMMAND "${CMAKE_COMMAND}" -E copy "${self_outfile}" "${target}"
  )
  if(TARGET ${source})
    add_dependencies(${target} ${source})
  endif()
endfunction()
