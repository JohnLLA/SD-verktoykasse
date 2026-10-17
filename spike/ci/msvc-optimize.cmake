# Lastes via CMAKE_PROJECT_INCLUDE. cmake-rs (brukt av whisper-rs-sys) overstyrer
# CMAKE_C(XX)_FLAGS_RELEASE med bare "-nologo -MD -Brepro -W0", så ggml ellers
# bygges uten /O2 på MSVC (tiden for 2 s lyd: 230 s mot 4 s på Mac).
if(MSVC)
  set(CMAKE_C_FLAGS_RELEASE "/O2 /Ob2 /DNDEBUG -nologo -MD -Brepro -W0")
  set(CMAKE_CXX_FLAGS_RELEASE "/O2 /Ob2 /DNDEBUG /utf-8 -nologo -MD -Brepro -W0")
endif()
