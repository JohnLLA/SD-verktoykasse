# Lastes via CMAKE_PROJECT_INCLUDE (se .cargo/config.toml i roten av repoet).
# cmake-rs (brukt av whisper-rs-sys) overstyrer CMAKE_C(XX)_FLAGS_RELEASE med bare
# "-nologo -MD -Brepro -W0", så ggml ellers bygges uten /O2 på MSVC
# (spiken: 2 s lyd tok 230 s uten, 16 s med). Gjør ingenting utenfor MSVC.
if(MSVC)
  set(CMAKE_C_FLAGS_RELEASE "/O2 /Ob2 /DNDEBUG -nologo -MD -Brepro -W0")
  set(CMAKE_CXX_FLAGS_RELEASE "/O2 /Ob2 /DNDEBUG /utf-8 -nologo -MD -Brepro -W0")
endif()
