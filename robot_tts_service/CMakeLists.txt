cmake_minimum_required(VERSION 3.10)
project(robot_tts_service)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 查找 unitree_sdk2
find_package(unitree_sdk2 REQUIRED)

# 编译 tts_speak 可执行文件
add_executable(tts_speak
    tts_speak.cpp
)

target_link_libraries(tts_speak
    unitree_sdk2
)

# 安装到 bin 目录
install(TARGETS tts_speak
    RUNTIME DESTINATION bin
)
