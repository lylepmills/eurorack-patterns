# Optional board-adapter checks; the default library build never enters here.
get_property(ep_tests_before_bench DIRECTORY PROPERTY TESTS)
ep_test(test_daisy_bench tests/test_daisy_bench.cpp)
ep_test(test_daisy_experiment tests/test_daisy_experiment.cpp)
ep_test(test_daisy_load tests/test_daisy_load.cpp)
ep_test(test_daisy_diagnostics tests/test_daisy_diagnostics.cpp)
ep_test(test_daisy_pulse_generator tests/test_daisy_pulse_generator.cpp)
ep_test(test_daisy_jack tests/test_daisy_jack.cpp)
ep_test(test_daisy_jack_faults tests/test_daisy_jack_faults.cpp)
ep_test(test_daisy_jack_acquisition tests/test_daisy_jack_acquisition.cpp)
ep_test(test_daisy_dsp tests/test_daisy_dsp.cpp)
ep_test(daisy_fault_sweep examples/daisy/fault_sweep.cpp)
add_executable(daisy_replay examples/daisy/replay.cpp)
target_link_libraries(daisy_replay PRIVATE eurorack_patterns)
set_target_properties(daisy_replay PROPERTIES CXX_STANDARD 11 CXX_STANDARD_REQUIRED YES CXX_EXTENSIONS NO)
if(MSVC)
  target_compile_options(daisy_replay PRIVATE /W4 /WX /permissive-)
else()
  target_compile_options(daisy_replay PRIVATE -Wall -Wextra -Wpedantic -Werror -fno-exceptions -fno-rtti)
endif()
if(EURORACK_PATTERNS_SANITIZERS)
  target_compile_options(daisy_replay PRIVATE -fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer)
  target_link_options(daisy_replay PRIVATE -fsanitize=address,undefined -fno-sanitize-recover=all)
endif()
add_test(NAME test_daisy_capture COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_daisy_capture.py $<TARGET_FILE:daisy_replay>)
add_test(NAME test_daisy_pulse_capture COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_daisy_pulse_capture.py)
add_test(NAME test_daisy_jack_capture COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_daisy_jack_capture.py $<TARGET_FILE:test_daisy_jack>)
add_test(NAME test_daisy_jack_fault_capture COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_daisy_jack_fault_capture.py $<TARGET_FILE:test_daisy_jack_faults>)

add_test(NAME test_daisy_jack_session COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_daisy_jack_session.py)
add_test(NAME test_daisy_jack_matrix COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_daisy_jack_matrix.py $<TARGET_FILE:test_daisy_jack_faults>)
add_test(NAME test_daisy_jack_load COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_daisy_jack_load.py $<TARGET_FILE:test_daisy_jack_faults>)
add_test(NAME test_daisy_jack_acquisition_capture COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_daisy_jack_acquisition_capture.py $<TARGET_FILE:test_daisy_jack_acquisition>)
add_test(NAME test_daisy_dsp_capture COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_daisy_dsp_capture.py $<TARGET_FILE:test_daisy_jack_acquisition> $<TARGET_FILE:test_daisy_dsp>)
add_test(NAME test_daisy_dma_memory COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_daisy_dma_memory.py $<TARGET_FILE:test_daisy_jack_acquisition> $<TARGET_FILE:test_daisy_dsp>)
add_test(NAME test_daisy_dma_placement COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_daisy_dma_placement.py $<TARGET_FILE:test_daisy_jack_acquisition> $<TARGET_FILE:test_daisy_dsp>)
add_test(NAME test_daisy_dma_alignment COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_daisy_dma_alignment.py $<TARGET_FILE:test_daisy_jack_acquisition> $<TARGET_FILE:test_daisy_dsp>)




add_test(NAME test_daisy_clock COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_daisy_clock.py $<TARGET_FILE:test_daisy_jack_acquisition> $<TARGET_FILE:test_daisy_dsp>)









add_test(NAME test_daisy_button_campaign COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_daisy_button_campaign.py)


add_test(NAME test_daisy_scope COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_daisy_scope.py)


add_test(NAME test_daisy_load_capture COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_daisy_load_capture.py $<TARGET_FILE:daisy_replay>)
add_test(NAME test_daisy_diagnostic_capture COMMAND ${Python3_EXECUTABLE}
  ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_daisy_diagnostic_capture.py $<TARGET_FILE:test_daisy_diagnostics> $<TARGET_FILE:daisy_replay>)






if(EURORACK_PATTERNS_BUILD_MEASURED_TESTS)
  add_test(NAME test_daisy_jack_measured COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_daisy_jack_measured.py)
  add_test(NAME test_daisy_dma_alignment_measured COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_daisy_dma_alignment_measured.py $<TARGET_FILE:test_daisy_dsp>)
  add_test(NAME test_daisy_dma_placement_measured COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_daisy_dma_placement_measured.py $<TARGET_FILE:test_daisy_dsp>)
  add_test(NAME test_daisy_firmware_comparison_measured COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_daisy_firmware_comparison_measured.py $<TARGET_FILE:test_daisy_dsp>)
  add_test(NAME test_daisy_dma_memory_measured COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_daisy_dma_memory_measured.py $<TARGET_FILE:test_daisy_dsp>)
  add_test(NAME test_daisy_reference COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_daisy_reference.py)
  add_test(NAME test_daisy_clock_reference COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_daisy_clock_reference.py $<TARGET_FILE:test_daisy_jack_acquisition> $<TARGET_FILE:test_daisy_dsp>)
  add_test(NAME test_daisy_clock_reference_measured COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_daisy_clock_reference_measured.py $<TARGET_FILE:test_daisy_dsp>)
  add_test(NAME test_daisy_hse_measured COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_daisy_hse_measured.py $<TARGET_FILE:test_daisy_dsp>)
  add_test(NAME test_daisy_jack_audio_measured COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_daisy_jack_audio_measured.py)
  add_test(NAME test_daisy_jack_scheduled_measured COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_daisy_jack_scheduled_measured.py)
  add_test(NAME test_daisy_jack_dsp_measured COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_daisy_jack_dsp_measured.py $<TARGET_FILE:test_daisy_dsp>)
  add_test(NAME test_daisy_jack_matrix_measured COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_daisy_jack_matrix_measured.py)
  add_test(NAME test_daisy_jack_motion COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_daisy_jack_motion.py $<TARGET_FILE:test_daisy_jack>)
  add_test(NAME test_daisy_automated_measured COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_daisy_automated_measured.py $<TARGET_FILE:daisy_replay>)
  add_test(NAME test_daisy_measured COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_daisy_measured.py $<TARGET_FILE:daisy_replay>)
  add_test(NAME test_daisy_timing_investigation COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_daisy_timing_investigation.py)
  add_test(NAME test_daisy_fault_measured COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_daisy_fault_measured.py $<TARGET_FILE:daisy_replay>)
  add_test(NAME test_daisy_load_measured COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_daisy_load_measured.py $<TARGET_FILE:daisy_replay>)
  add_test(NAME test_daisy_timing_measured COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_daisy_timing_measured.py)
  add_test(NAME test_daisy_manual_load_measured COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_daisy_manual_load_measured.py $<TARGET_FILE:daisy_replay>)
  add_test(NAME test_daisy_interaction_measured COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_daisy_interaction_measured.py $<TARGET_FILE:daisy_replay>)
  add_test(NAME test_daisy_loaded_fault_measured COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_daisy_loaded_fault_measured.py $<TARGET_FILE:daisy_replay>)
endif()
get_property(ep_bench_tests DIRECTORY PROPERTY TESTS)
list(REMOVE_ITEM ep_bench_tests ${ep_tests_before_bench})
set_tests_properties(${ep_bench_tests} PROPERTIES LABELS "bench")
if(EURORACK_PATTERNS_BUILD_MEASURED_TESTS)
  set_tests_properties(test_daisy_jack_measured test_daisy_dma_alignment_measured test_daisy_dma_placement_measured test_daisy_firmware_comparison_measured test_daisy_dma_memory_measured test_daisy_reference test_daisy_clock_reference test_daisy_clock_reference_measured test_daisy_hse_measured test_daisy_jack_audio_measured test_daisy_jack_scheduled_measured test_daisy_jack_dsp_measured test_daisy_jack_matrix_measured test_daisy_jack_motion test_daisy_automated_measured test_daisy_measured test_daisy_timing_investigation test_daisy_fault_measured test_daisy_load_measured test_daisy_timing_measured test_daisy_manual_load_measured test_daisy_interaction_measured test_daisy_loaded_fault_measured PROPERTIES LABELS "bench;measured")
endif()
