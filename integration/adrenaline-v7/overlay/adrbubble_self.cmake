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

if(NOT EXISTS "${ADRBUBBLE_MAKE_FSELF}")
  message(FATAL_ERROR
    "ADRBUBBLE_MAKE_FSELF does not exist: ${ADRBUBBLE_MAKE_FSELF}\n"
    "Build vita-toolchain 25d343b with the AdrBubbleBooter OSS patch."
  )
endif()

function(adrbubble_create_self target source module_nid)
  set(options UNCOMPRESSED UNSAFE)
  set(one_value_args CONFIG ELF_CREATE)
  cmake_parse_arguments(adr_self "${options}" "${one_value_args}" "" ${ARGN})

  if(adr_self_ELF_CREATE)
    set(elf_create "${adr_self_ELF_CREATE}")
  else()
    set(elf_create "${ADRBUBBLE_ELF_CREATE}")
  endif()
  if(NOT EXISTS "${elf_create}")
    message(FATAL_ERROR "vita-elf-create does not exist: ${elf_create}")
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

  if(TARGET ${source})
    set(sourcepath "${CMAKE_CURRENT_BINARY_DIR}/${source}")
  else()
    set(sourcepath "${source}")
  endif()
  get_filename_component(sourcefile "${sourcepath}" NAME)

  set(velf "${CMAKE_CURRENT_BINARY_DIR}/${sourcefile}.velf")
  add_custom_command(
    OUTPUT "${velf}"
    COMMAND "${elf_create}" ${elf_create_flags} "${sourcepath}" "${velf}"
    DEPENDS "${sourcepath}" ${elf_create_dependencies}
    COMMENT "Converting to Sony ELF ${sourcefile}.velf"
    VERBATIM
  )

  set(self_outfile "${CMAKE_CURRENT_BINARY_DIR}/${target}.out")
  add_custom_command(
    OUTPUT "${self_outfile}"
    COMMAND "${ADRBUBBLE_MAKE_FSELF}" ${make_fself_flags} "${velf}" "${self_outfile}"
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
