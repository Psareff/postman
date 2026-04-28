cmake_minimum_required(VERSION 3.20)
project(email_system CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
SET(CMAKE_FIND_LIBRARY_SUFFIXES ".a")
SET(BUILD_SHARED_LIBRARIES OFF)
SET(CMAKE_EXE_LINKER_FLAGS "-static")

include(FetchContent)

FetchContent_Declare(asio
        GIT_REPOSITORY https://github.com/chriskohlhoff/asio.git
        GIT_TAG asio-1-30-2
)
FetchContent_MakeAvailable(asio)

add_library(asio_lib INTERFACE)

target_include_directories(asio_lib INTERFACE ${asio_SOURCE_DIR}/asio/include)
target_compile_definitions(asio_lib INTERFACE ASIO_STANDALONE)

find_package(Threads REQUIRED)
target_link_libraries(asio_lib INTERFACE Threads::Threads)
if (WIN32)
    target_link_libraries(asio_lib INTERFACE ws2_32 wsock32)
endif ()

add_executable(postman postman/main.cpp)
target_link_libraries(postman PRIVATE asio_lib)
target_include_directories(postman PRIVATE ${CMAKE_SOURCE_DIR})

add_executable(mail mail/main.cpp)
target_link_libraries(mail PRIVATE asio_lib)
target_include_directories(mail PRIVATE ${CMAKE_SOURCE_DIR})
