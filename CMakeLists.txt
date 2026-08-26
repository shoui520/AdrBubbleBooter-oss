cmake_minimum_required(VERSION 3.10)

if(NOT DEFINED CMAKE_TOOLCHAIN_FILE)
  if(DEFINED ENV{VITASDK})
    set(CMAKE_TOOLCHAIN_FILE
      "$ENV{VITASDK}/share/vita.toolchain.cmake"
      CACHE PATH "VitaSDK toolchain file"
    )
  else()
    message(FATAL_ERROR "Set VITASDK or pass CMAKE_TOOLCHAIN_FILE")
  endif()
endif()

project(AdrBubbleBooterOSS C)
include("${VITASDK}/share/vita.cmake" REQUIRED)
include("${CMAKE_CURRENT_SOURCE_DIR}/cmake/AdrBubbleSelf.cmake" REQUIRED)

option(
  ADRBUBBLE_ISAGE_CONFIG
  "Use the compact Adrenaline 8 Vita configuration layout"
  OFF
)

set(
  ADRBUBBLE_ADR_ELF_CREATE
  "${ADRBUBBLE_ELF_CREATE}"
  CACHE FILEPATH
  "vita-elf-create generation matching the tested adrbubblebooter metadata"
)

set(
  ADRBUBBLE_LIBK_SOURCE
  ""
  CACHE PATH
  "Pinned DaveeFTW/TeamMolecule libk source used by the recovered modules"
)
if(NOT EXISTS "${ADRBUBBLE_LIBK_SOURCE}/thirdparty/pdclib/functions/_PDCLIB/print.c")
  message(FATAL_ERROR "ADRBUBBLE_LIBK_SOURCE must name the pinned libk source tree")
endif()

add_subdirectory(src/vita/adrbubblebooter)
add_subdirectory(src/vita/bootconv)
add_subdirectory(src/vita/ebooter)
