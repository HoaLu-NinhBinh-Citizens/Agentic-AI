CMAKE_MINIMUM_REQUIRED(VERSION 3.26.3)

# Set up general project
SET(CMAKE_SYSTEM_NAME Generic)
SET(CMAKE_EXECUTABLE_SUFFIX ".elf")

# Set the main project name
set(CMAKE_MAIN_PROJECT_NAME RemoteControl)

# Set the project name
set(CMAKE_PROJECT_NAME CarRemote)

# Set up tool compiler
SET(TOOLCHAIN_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../../../../../Tools/gcc)

# Choose tool compiler
SET(TARGET_TRIPLET "arm-none-eabi")
SET(TOOLCHAIN_BIN_DIR ${TOOLCHAIN_DIR}/bin)
SET(CMAKE_C_COMPILER ${TOOLCHAIN_BIN_DIR}/${TARGET_TRIPLET}-gcc.exe)
set(CMAKE_C_COMPILER_FORCED TRUE)
set(CMAKE_CXX_COMPILER_FORCED TRUE)

# Enable CMake support for ASM languages
enable_language(ASM)

# Core project settings
project(${CMAKE_PROJECT_NAME})
SET(PROJECT_NAME ${CMAKE_PROJECT_NAME}.elf)

# Set build output
set(ProjDirPath "${CMAKE_CURRENT_SOURCE_DIR}")
SET(EXECUTABLE_OUTPUT_PATH ${ProjDirPath}/../../../../../output/${CMAKE_MAIN_PROJECT_NAME})

# Sources paths
add_executable (${PROJECT_NAME}
    "${CMAKE_CURRENT_SOURCE_DIR}/Config/Src/freertos.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/Config/Src/stm32f4xx_hal_timebase_tim.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/Main/Src/main.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/Startup/Src/startup_stm32f407xx.s"
    "${CMAKE_CURRENT_SOURCE_DIR}/Startup/Src/stm32f4xx_hal_msp.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/Startup/Src/stm32f4xx_it.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/Startup/Src/syscalls.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/Startup/Src/sysmem.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/Startup/Src/system_stm32f4xx.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../../Driver/Chip/Stm32F407/Src/stm32f4xx_hal_tim.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../../Driver/Chip/Stm32F407/Src/stm32f4xx_hal_tim_ex.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../../Driver/Chip/Stm32F407/Src/stm32f4xx_hal_rcc.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../../Driver/Chip/Stm32F407/Src/stm32f4xx_hal_rcc_ex.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../../Driver/Chip/Stm32F407/Src/stm32f4xx_hal_flash.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../../Driver/Chip/Stm32F407/Src/stm32f4xx_hal_flash_ex.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../../Driver/Chip/Stm32F407/Src/stm32f4xx_hal_flash_ramfunc.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../../Driver/Chip/Stm32F407/Src/stm32f4xx_hal_gpio.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../../Driver/Chip/Stm32F407/Src/stm32f4xx_hal_dma_ex.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../../Driver/Chip/Stm32F407/Src/stm32f4xx_hal_dma.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../../Driver/Chip/Stm32F407/Src/stm32f4xx_hal_pwr.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../../Driver/Chip/Stm32F407/Src/stm32f4xx_hal_pwr_ex.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../../Driver/Chip/Stm32F407/Src/stm32f4xx_hal_cortex.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../../Driver/Chip/Stm32F407/Src/stm32f4xx_hal.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../../Driver/Chip/Stm32F407/Src/stm32f4xx_hal_exti.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../../Kernel/FreeRTOS/Source/croutine.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../../Kernel/FreeRTOS/Source/event_groups.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../../Kernel/FreeRTOS/Source/list.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../../Kernel/FreeRTOS/Source/queue.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../../Kernel/FreeRTOS/Source/stream_buffer.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../../Kernel/FreeRTOS/Source/tasks.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../../Kernel/FreeRTOS/Source/timers.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../../Kernel/FreeRTOS/Source/CMSIS_RTOS/cmsis_os.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../../Kernel/FreeRTOS/Source/portable/MemMang/heap_4.c"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../../Kernel/FreeRTOS/Source/portable/GCC/ARM_CM4F/port.c"
)

# Include paths
target_include_directories (${PROJECT_NAME} PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}/Config/Inc"
    "${CMAKE_CURRENT_SOURCE_DIR}/Main/Inc"
    "${CMAKE_CURRENT_SOURCE_DIR}/Startup/Inc"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../../Driver/Chip/Stm32F407/Inc"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../../Driver/Chip/Stm32F407/Inc/Legacy"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../../Driver/CMSIS/Device/ST/STM32F4xx/Include"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../../Driver/CMSIS/Include"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../../Kernel/FreeRTOS/Source/include"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../../Kernel/FreeRTOS/Source/CMSIS_RTOS"
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../../Kernel/FreeRTOS/Source/portable/GCC/ARM_CM4F"
)

# Compiler define
target_compile_definitions (${PROJECT_NAME} PRIVATE
    "USE_HAL_DRIVER"
    "STM32F407xx"
)

# CC flags
target_compile_options (${PROJECT_NAME} PRIVATE
    $<$<COMPILE_LANGUAGE:C>:-mcpu=cortex-m4>
    $<$<COMPILE_LANGUAGE:C>:-mfpu=fpv4-sp-d16>
    $<$<COMPILE_LANGUAGE:C>:-mfloat-abi=hard>
    $<$<COMPILE_LANGUAGE:C>:-Wall>
    $<$<COMPILE_LANGUAGE:C>:-Wextra>
    $<$<COMPILE_LANGUAGE:C>:-Wpedantic>
    $<$<COMPILE_LANGUAGE:C>:-fdata-sections>
    $<$<COMPILE_LANGUAGE:C>:-ffunction-sections>
    $<$<COMPILE_LANGUAGE:C>:-O0>
    $<$<COMPILE_LANGUAGE:C>:-g3>
)

# ASM flags
SET (CMAKE_ASM_FLAGS " \
    ${CMAKE_ASM_FLAGS} \
    -mcpu=cortex-m4 \
    -mfpu=fpv4-sp-d16 \
    -mfloat-abi=hard \
    -x assembler-with-cpp \
    -MMD \
    -MP \ "
)

# LK flags
SET (CMAKE_EXE_LINKER_FLAGS " \
    ${CMAKE_EXE_LINKER_FLAGS} \
    -mcpu=cortex-m4 \
    -mfpu=fpv4-sp-d16 \
    -mfloat-abi=hard \
    -T \ ${CMAKE_CURRENT_SOURCE_DIR}/Linker/STM32F407XX_FLASH.ld \
    -specs=nano.specs \
    -Wl,-Map=${CMAKE_CURRENT_SOURCE_DIR}/../../../../../output/${CMAKE_MAIN_PROJECT_NAME}/${CMAKE_PROJECT_NAME}.map \
    -Wl,--gc-sections \
    -Wl,--start-group \
    -lc \
    -lm \
    -Wl,--end-group \
    -Wl,--print-memory-usage \ "
)

target_link_libraries(${CMAKE_PROJECT_NAME}.elf PRIVATE)
