/**
 * tts_speak.cpp - 简单的 TTS 命令行程序
 * 
 * 用法: ./tts_speak "要播放的文字" [网络接口] [语言]
 *   网络接口: eth0 (默认)
 *   语言: 0=自动, 1=英文 (默认 0)
 * 
 * 编译:
 *   mkdir build && cd build
 *   cmake ..
 *   make
 */

#include <iostream>
#include <string>
#include <unitree/robot/channel/channel_factory.hpp>
#include <unitree/robot/g1/audio/g1_audio_client.hpp>
#include <unitree/common/time/time_tool.hpp>

int main(int argc, char* argv[]) {
    if (argc < 2) {
        std::cerr << "用法: " << argv[0] << " \"文字\" [网络接口] [语言]" << std::endl;
        std::cerr << "  网络接口: eth0 (默认)" << std::endl;
        std::cerr << "  语言: 0=自动, 1=英文 (默认 0)" << std::endl;
        return 1;
    }
    
    std::string text = argv[1];
    std::string network_interface = (argc >= 3) ? argv[2] : "eth0";
    int lang = (argc >= 4) ? std::stoi(argv[3]) : 0;
    
    try {
        // 初始化 Channel
        unitree::robot::ChannelFactory::Instance()->Init(0, network_interface.c_str());
        
        // 创建 AudioClient
        unitree::robot::g1::AudioClient client;
        client.Init();
        client.SetTimeout(10.0f);
        
        // 设置音量为 100%
        client.SetVolume(100);
        
        // 调用 TTS
        int32_t ret = client.TtsMaker(text, lang);
        
        if (ret != 0) {
            std::cerr << "TtsMaker 调用失败: " << ret << std::endl;
            return 1;
        }
        
        // 等待播放完成（根据文字长度估算）
        // 大约每个字符 200ms
        int wait_time = std::max(3, static_cast<int>(text.length() * 0.2));
        unitree::common::Sleep(wait_time);
        
        std::cout << "播放完成" << std::endl;
        return 0;
        
    } catch (const std::exception& e) {
        std::cerr << "错误: " << e.what() << std::endl;
        return 1;
    }
}
