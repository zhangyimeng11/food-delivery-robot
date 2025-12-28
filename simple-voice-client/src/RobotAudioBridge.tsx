/**
 * Robot Audio Bridge - 将 Agent 音频转发到机器人
 * 
 * 拦截 LiveKit 远程音频轨道，转换为 PCM 数据，通过 WebSocket 发送到机器人。
 */

import { useEffect, useRef, useCallback, useState } from 'react'
import { useRoomContext } from '@livekit/components-react'
import { Track, RemoteTrack, RemoteAudioTrack, RoomEvent } from 'livekit-client'

// 机器人 WebSocket 配置
const ROBOT_WS_URL = 'ws://192.168.0.13:8765'

// 音频配置（目标格式：16kHz, 单声道, 16bit）
const TARGET_SAMPLE_RATE = 16000

interface RobotAudioBridgeState {
    connected: boolean
    error: string | null
    bytesSent: number
}

/**
 * 音频重采样器
 * 将任意采样率转换为 16kHz
 */
function resampleAudio(
    inputBuffer: Float32Array,
    inputSampleRate: number,
    outputSampleRate: number
): Float32Array {
    if (inputSampleRate === outputSampleRate) {
        return inputBuffer
    }

    const ratio = inputSampleRate / outputSampleRate
    const outputLength = Math.floor(inputBuffer.length / ratio)
    const output = new Float32Array(outputLength)

    for (let i = 0; i < outputLength; i++) {
        const srcIndex = i * ratio
        const srcIndexFloor = Math.floor(srcIndex)
        const srcIndexCeil = Math.min(srcIndexFloor + 1, inputBuffer.length - 1)
        const t = srcIndex - srcIndexFloor

        // 线性插值
        output[i] = inputBuffer[srcIndexFloor] * (1 - t) + inputBuffer[srcIndexCeil] * t
    }

    return output
}

/**
 * 将 Float32 音频数据转换为 16bit PCM
 */
function float32ToPCM16(float32Array: Float32Array): ArrayBuffer {
    const buffer = new ArrayBuffer(float32Array.length * 2)
    const view = new DataView(buffer)

    for (let i = 0; i < float32Array.length; i++) {
        // 限制范围到 [-1, 1]
        const s = Math.max(-1, Math.min(1, float32Array[i]))
        // 转换为 16-bit 整数
        const val = s < 0 ? s * 0x8000 : s * 0x7FFF
        view.setInt16(i * 2, val, true) // little-endian
    }

    return buffer
}

/**
 * Robot Audio Bridge Hook
 * 
 * 将 Agent 的音频输出转发到机器人
 */
export function useRobotAudioBridge(enabled: boolean = true): RobotAudioBridgeState {
    const room = useRoomContext()

    const wsRef = useRef<WebSocket | null>(null)
    const audioContextRef = useRef<AudioContext | null>(null)
    const processorRef = useRef<ScriptProcessorNode | null>(null)
    const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null)
    const isConnectingRef = useRef(false)
    const hasProcessorRef = useRef(false)

    const [state, setState] = useState<RobotAudioBridgeState>({
        connected: false,
        error: null,
        bytesSent: 0,
    })

    const bytesSentRef = useRef(0)

    // 连接到机器人 WebSocket（只调用一次）
    const connectToRobot = useCallback(() => {
        // 防止重复连接
        if (wsRef.current?.readyState === WebSocket.OPEN ||
            wsRef.current?.readyState === WebSocket.CONNECTING ||
            isConnectingRef.current) {
            return
        }

        isConnectingRef.current = true
        console.log('[RobotAudioBridge] Connecting to robot...', ROBOT_WS_URL)

        const ws = new WebSocket(ROBOT_WS_URL)

        ws.onopen = () => {
            console.log('[RobotAudioBridge] Connected to robot!')
            isConnectingRef.current = false
            setState(s => ({ ...s, connected: true, error: null }))
            // 通知机器人开始新流
            ws.send(JSON.stringify({ type: 'new_stream' }))
        }

        ws.onclose = () => {
            console.log('[RobotAudioBridge] Disconnected from robot')
            isConnectingRef.current = false
            setState(s => ({ ...s, connected: false }))
            wsRef.current = null
        }

        ws.onerror = (e) => {
            console.error('[RobotAudioBridge] WebSocket error:', e)
            isConnectingRef.current = false
            setState(s => ({ ...s, error: 'Connection failed' }))
        }

        ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data)
                console.log('[RobotAudioBridge] Robot response:', msg)
            } catch {
                // Ignore non-JSON messages
            }
        }

        wsRef.current = ws
    }, [])

    // 发送 PCM 数据到机器人
    const sendAudioToRobot = useCallback((pcmData: ArrayBuffer) => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(pcmData)
            bytesSentRef.current += pcmData.byteLength

            // 每 50KB 更新一次状态并打印日志
            if (bytesSentRef.current % 51200 < pcmData.byteLength) {
                console.log(`[RobotAudioBridge] Sent ${(bytesSentRef.current / 1024).toFixed(1)} KB`)
                setState(s => ({ ...s, bytesSent: bytesSentRef.current }))
            }
        }
    }, [])

    // 处理远程音频轨道
    const processRemoteAudioTrack = useCallback((track: RemoteAudioTrack) => {
        // 防止重复处理
        if (hasProcessorRef.current) {
            console.log('[RobotAudioBridge] Already processing audio, skip')
            return
        }

        hasProcessorRef.current = true
        console.log('[RobotAudioBridge] Processing remote audio track')

        // 获取音频流
        const mediaStream = new MediaStream([track.mediaStreamTrack])

        // 创建 AudioContext
        if (!audioContextRef.current) {
            audioContextRef.current = new AudioContext({ sampleRate: 48000 })
        }
        const audioContext = audioContextRef.current

        // 创建源节点
        const source = audioContext.createMediaStreamSource(mediaStream)
        sourceNodeRef.current = source

        // 使用 ScriptProcessorNode 处理音频
        // 缓冲区大小：4096 样本 ≈ 85ms @ 48kHz
        const processor = audioContext.createScriptProcessor(4096, 1, 1)
        processorRef.current = processor

        let chunkCount = 0
        let totalFrames = 0
        processor.onaudioprocess = (event) => {
            const inputData = event.inputBuffer.getChannelData(0)
            totalFrames++

            // 计算音频峰值
            let maxSample = 0
            for (let i = 0; i < inputData.length; i++) {
                const abs = Math.abs(inputData[i])
                if (abs > maxSample) maxSample = abs
            }

            // 每 50 帧打印一次调试信息（约每 4 秒）
            if (totalFrames % 50 === 1) {
                console.log(`[RobotAudioBridge] Frame ${totalFrames}, max sample: ${maxSample.toFixed(6)}, ws: ${wsRef.current?.readyState}`)
            }

            // 只有有音频数据才发送（但阈值降低到可以检测到极小的信号）
            if (maxSample < 0.0001) {
                return // 完全静音才跳过
            }

            chunkCount++

            // 重采样到 16kHz
            const resampledData = resampleAudio(
                inputData,
                audioContext.sampleRate,
                TARGET_SAMPLE_RATE
            )

            // 转换为 16bit PCM
            const pcmData = float32ToPCM16(resampledData)

            // 发送到机器人
            sendAudioToRobot(pcmData)
        }

        // 连接节点
        source.connect(processor)
        // 创建一个静音目标节点，避免音频输出到扬声器
        const silentDestination = audioContext.createGain()
        silentDestination.gain.value = 0
        silentDestination.connect(audioContext.destination)
        processor.connect(silentDestination)

        console.log('[RobotAudioBridge] Audio processing started')
    }, [sendAudioToRobot])

    // 清理音频处理器
    const cleanupAudioProcessor = useCallback(() => {
        if (processorRef.current) {
            processorRef.current.disconnect()
            processorRef.current = null
        }
        if (sourceNodeRef.current) {
            sourceNodeRef.current.disconnect()
            sourceNodeRef.current = null
        }
        hasProcessorRef.current = false
    }, [])

    // 建立 WebSocket 连接（只在组件挂载时）
    useEffect(() => {
        if (!enabled) return

        connectToRobot()

        return () => {
            // 清理 WebSocket
            if (wsRef.current) {
                if (wsRef.current.readyState === WebSocket.OPEN) {
                    wsRef.current.send(JSON.stringify({ type: 'finish' }))
                }
                wsRef.current.close()
                wsRef.current = null
            }
        }
    }, [enabled, connectToRobot])

    // 监听远程参与者的音频轨道（独立的 effect）
    useEffect(() => {
        if (!enabled || !room) return

        // 监听轨道订阅事件
        const handleTrackSubscribed = (
            track: RemoteTrack,
            _publication: any,
            participant: any
        ) => {
            console.log('[RobotAudioBridge] Track subscribed:', track.kind, participant.identity)

            if (track.kind === Track.Kind.Audio) {
                // 确保 WebSocket 已连接
                if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
                    connectToRobot()
                }
                // 处理音频轨道
                processRemoteAudioTrack(track as RemoteAudioTrack)
            }
        }

        const handleTrackUnsubscribed = (track: RemoteTrack) => {
            console.log('[RobotAudioBridge] Track unsubscribed:', track.kind)
            if (track.kind === Track.Kind.Audio) {
                cleanupAudioProcessor()
            }
        }

        room.on(RoomEvent.TrackSubscribed, handleTrackSubscribed)
        room.on(RoomEvent.TrackUnsubscribed, handleTrackUnsubscribed)

        // 检查已存在的音频轨道
        room.remoteParticipants.forEach((participant) => {
            participant.audioTrackPublications.forEach((pub) => {
                if (pub.track && pub.isSubscribed) {
                    console.log('[RobotAudioBridge] Found existing audio track')
                    processRemoteAudioTrack(pub.track as RemoteAudioTrack)
                }
            })
        })

        return () => {
            room.off(RoomEvent.TrackSubscribed, handleTrackSubscribed)
            room.off(RoomEvent.TrackUnsubscribed, handleTrackUnsubscribed)
            cleanupAudioProcessor()

            // 关闭 AudioContext
            if (audioContextRef.current) {
                audioContextRef.current.close()
                audioContextRef.current = null
            }
        }
    }, [enabled, room, connectToRobot, processRemoteAudioTrack, cleanupAudioProcessor])

    return state
}

/**
 * Robot Audio Bridge 组件
 * 
 * 使用方式：在 LiveKitRoom 内部添加此组件
 */
export function RobotAudioBridge({ enabled = true }: { enabled?: boolean }) {
    const state = useRobotAudioBridge(enabled)

    // 可选：显示状态指示器
    if (!enabled) return null

    return (
        <div style={{
            position: 'fixed',
            bottom: '10px',
            right: '10px',
            padding: '8px 12px',
            background: state.connected ? 'rgba(74, 222, 128, 0.2)' : 'rgba(239, 68, 68, 0.2)',
            border: `1px solid ${state.connected ? 'rgba(74, 222, 128, 0.4)' : 'rgba(239, 68, 68, 0.4)'}`,
            borderRadius: '8px',
            fontSize: '12px',
            color: state.connected ? '#4ade80' : '#ef4444',
            zIndex: 1000,
        }}>
            🤖 {state.connected ? '机器人已连接' : '机器人未连接'}
            {state.connected && state.bytesSent > 0 && (
                <span style={{ marginLeft: '8px', opacity: 0.7 }}>
                    {(state.bytesSent / 1024).toFixed(1)} KB
                </span>
            )}
            {state.error && (
                <span style={{ marginLeft: '8px', color: '#fca5a5' }}>
                    {state.error}
                </span>
            )}
        </div>
    )
}
