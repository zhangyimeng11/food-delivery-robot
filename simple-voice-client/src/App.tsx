import { useState, useCallback, useEffect, useRef } from 'react'
import {
  LiveKitRoom,
  RoomAudioRenderer,
  useVoiceAssistant,
  BarVisualizer,
  useConnectionState,
  useTranscriptions,
  useLocalParticipant,
  useRoomContext,
} from '@livekit/components-react'
import { ConnectionState } from 'livekit-client'
import '@livekit/components-styles'

// ========== 配置 ==========
const CONFIG = {
  DEPLOYMENT_SLUG: '外卖助手-1765480093368',
  API_BASE_URL: '/api/v1',
  // 机器人 TTS 服务地址
  ROBOT_TTS_URL: 'http://192.168.0.13:8080',
}

// ========== 类型定义 ==========
interface SessionInfo {
  token: string
  url: string
  sessionId: string
}

interface ChatMessage {
  name: string
  message: string
  isSelf: boolean
  timestamp: number
}

// ========== 对话记录组件 ==========
function TranscriptionTile() {
  const transcriptions = useTranscriptions()
  const { localParticipant } = useLocalParticipant()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const messageMapRef = useRef<Map<string, ChatMessage>>(new Map())
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const newMessageMap = new Map(messageMapRef.current)
    let hasChanges = false

    transcriptions.forEach((transcription) => {
      const participantIdentity = transcription.participantInfo.identity
      const isLocal = participantIdentity === localParticipant.identity
      const streamId = `${participantIdentity}_${transcription.streamInfo.timestamp || Date.now()}`

      if (!newMessageMap.has(streamId) || newMessageMap.get(streamId)?.message !== transcription.text) {
        newMessageMap.set(streamId, {
          message: transcription.text,
          name: isLocal ? '你' : 'Agent',
          isSelf: isLocal,
          timestamp: transcription.streamInfo.timestamp || Date.now(),
        })
        hasChanges = true
      }
    })

    if (hasChanges) {
      messageMapRef.current = newMessageMap
      const sortedMessages = Array.from(newMessageMap.values()).sort(
        (a, b) => a.timestamp - b.timestamp
      )
      setMessages(sortedMessages)
    }
  }, [transcriptions, localParticipant.identity])

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [messages])

  return (
    <div ref={containerRef} style={styles.transcriptContainer}>
      {messages.length === 0 ? (
        <div style={styles.emptyTranscript}>
          <div style={{ fontSize: '48px', marginBottom: '16px' }}>💬</div>
          <div>对话内容将在这里显示</div>
        </div>
      ) : (
        messages.map((msg, index, allMsg) => {
          const hideName = index >= 1 && allMsg[index - 1].name === msg.name
          return (
            <div key={index} style={{ marginTop: hideName ? '6px' : '20px' }}>
              {!hideName && (
                <div style={{
                  fontSize: '12px',
                  fontWeight: 600,
                  color: msg.isSelf ? '#94a3b8' : '#60a5fa',
                  marginBottom: '6px',
                  textTransform: 'uppercase',
                }}>
                  {msg.name}
                </div>
              )}
              <div style={{
                fontSize: '15px',
                color: msg.isSelf ? '#cbd5e1' : '#f1f5f9',
                whiteSpace: 'pre-line',
                lineHeight: '1.7',
              }}>
                {msg.message}
              </div>
            </div>
          )
        })
      )}
    </div>
  )
}

// 监听 Agent 的回复，发送到机器人扬声器播放
function RobotTTSBridge() {
  const transcriptions = useTranscriptions()
  const { localParticipant } = useLocalParticipant()
  const sentTextsRef = useRef<Set<string>>(new Set())
  const pendingTextRef = useRef<string>('')
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    // 调试：打印所有 transcriptions
    console.log('[RobotTTS] Transcriptions updated:', transcriptions.length)

    // 找到所有 Agent 回复（非本地用户的）
    const agentTranscriptions = transcriptions.filter(
      (t) => t.participantInfo.identity !== localParticipant.identity
    )

    console.log('[RobotTTS] Agent transcriptions:', agentTranscriptions.length)

    if (agentTranscriptions.length === 0) return

    // 取最新的一条 Agent 回复
    const latest = agentTranscriptions[agentTranscriptions.length - 1]
    const text = latest.text?.trim()

    console.log('[RobotTTS] Latest agent text:', text?.substring(0, 100))

    if (!text || text.length < 2) return

    // 如果文本已经发送过，跳过
    if (sentTextsRef.current.has(text)) {
      return
    }

    // 使用防抖：等待 1 秒文本稳定后再发送
    pendingTextRef.current = text

    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current)
    }

    debounceTimerRef.current = setTimeout(() => {
      const currentText = pendingTextRef.current
      if (currentText && !sentTextsRef.current.has(currentText)) {
        console.log('[RobotTTS] Sending to robot after debounce:', currentText.substring(0, 50))
        sentTextsRef.current.add(currentText)

        // 发送到机器人 TTS 服务
        fetch(`${CONFIG.ROBOT_TTS_URL}/speak`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: currentText }),
          mode: 'cors',
        })
          .then((res) => {
            console.log('[RobotTTS] Response:', res.status)
          })
          .catch((error) => {
            console.error('[RobotTTS] Failed:', error)
          })
      }
    }, 1000) // 等待 1 秒文本稳定

    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current)
      }
    }
  }, [transcriptions, localParticipant.identity])

  // 这个组件不渲染任何内容
  return null
}

// ========== 禁用浏览器音频输出组件 ==========
// 静音所有远程参与者的音频轨道，避免浏览器播放
function DisableAudioOutput() {
  const room = useRoomContext()

  useEffect(() => {
    if (!room) return

    // 禁用所有远程音频轨道的播放
    const disableAudio = () => {
      room.remoteParticipants.forEach((participant) => {
        participant.audioTrackPublications.forEach((publication) => {
          if (publication.track) {
            // 将音频轨道静音
            const audioElement = publication.track.attachedElements[0] as HTMLAudioElement
            if (audioElement) {
              audioElement.muted = true
              audioElement.volume = 0
            }
          }
        })
      })
    }

    // 监听轨道订阅事件
    room.on('trackSubscribed', disableAudio)
    room.on('participantConnected', disableAudio)

    // 初始禁用
    disableAudio()

    return () => {
      room.off('trackSubscribed', disableAudio)
      room.off('participantConnected', disableAudio)
    }
  }, [room])

  return null
}

// ========== 语音助手 UI 组件 ==========
function VoiceAssistantUI() {
  const { state, audioTrack } = useVoiceAssistant()
  const connectionState = useConnectionState()

  const getStateText = () => {
    if (connectionState === ConnectionState.Connecting) return '连接中...'
    if (connectionState === ConnectionState.Reconnecting) return '重连中...'
    if (connectionState === ConnectionState.Disconnected) return '已断开'

    switch (state) {
      case 'connecting': return '连接中...'
      case 'initializing': return '初始化...'
      case 'listening': return '聆听中...'
      case 'thinking': return '思考中...'
      case 'speaking': return '讲话中...'
      default: return '准备中...'
    }
  }

  const getStateColor = () => {
    switch (state) {
      case 'listening': return '#4ade80'
      case 'thinking': return '#fbbf24'
      case 'speaking': return '#a78bfa'
      default: return '#94a3b8'
    }
  }

  return (
    <div style={styles.voiceContainer}>
      {/* 可视化波形 */}
      <div style={styles.visualizerWrapper}>
        <BarVisualizer
          state={state}
          barCount={5}
          trackRef={audioTrack}
          style={{ width: '100%', height: '100%' }}
        />
      </div>

      {/* 状态指示 */}
      <div style={{ ...styles.stateIndicator, color: getStateColor() }}>
        <span style={{ ...styles.stateDot, backgroundColor: getStateColor() }} />
        {getStateText()}
      </div>

      {/* 提示文字 */}
      <div style={styles.hint}>请直接与 Agent 对话</div>
    </div>
  )
}

// ========== 控制面板组件 ==========
function ControlPanel({ onRestart }: { onRestart: () => void }) {
  const { localParticipant } = useLocalParticipant()
  const room = useRoomContext()
  const [isMuted, setIsMuted] = useState(false)

  const toggleMute = async () => {
    if (localParticipant) {
      const newMutedState = !isMuted
      await localParticipant.setMicrophoneEnabled(!newMutedState)
      setIsMuted(newMutedState)
    }
  }

  const endSession = () => {
    if (room) {
      room.disconnect()
    }
  }

  return (
    <div style={styles.controlPanel}>
      <button
        onClick={toggleMute}
        style={{
          ...styles.controlButton,
          background: isMuted ? 'rgba(239, 68, 68, 0.2)' : 'rgba(74, 222, 128, 0.2)',
          borderColor: isMuted ? 'rgba(239, 68, 68, 0.3)' : 'rgba(74, 222, 128, 0.3)',
        }}
      >
        {isMuted ? '🔇 取消静音' : '🎤 静音'}
      </button>

      <button onClick={onRestart} style={styles.controlButton}>
        🔄 重新开始
      </button>

      <button
        onClick={endSession}
        style={{
          ...styles.controlButton,
          background: 'rgba(239, 68, 68, 0.2)',
          borderColor: 'rgba(239, 68, 68, 0.3)',
        }}
      >
        📞 结束会话
      </button>
    </div>
  )
}

// ========== 会话界面组件 ==========
function AgentSessionUI({ onRestart }: { onRestart: () => void }) {
  return (
    <div style={styles.sessionContainer}>
      {/* 左右分栏 */}
      <div style={styles.mainContent}>
        {/* 左侧：语音交互 */}
        <div style={styles.leftPanel}>
          <VoiceAssistantUI />
        </div>

        {/* 右侧：对话记录 */}
        <div style={styles.rightPanel}>
          <div style={styles.transcriptHeader}>
            <span style={{ fontSize: '16px' }}>💬</span>
            <span>实时对话</span>
          </div>
          <TranscriptionTile />
        </div>
      </div>

      {/* 底部控制面板 */}
      <ControlPanel onRestart={onRestart} />
    </div>
  )
}

// ========== 主应用组件 ==========
export default function App() {
  const [sessionInfo, setSessionInfo] = useState<SessionInfo | null>(null)
  const [connecting, setConnecting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // 创建会话（可带开场白）
  const startSession = useCallback(async (presetMessage?: string) => {
    setConnecting(true)
    setError(null)

    try {
      const userIdentity = `user_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`

      const requestBody: Record<string, unknown> = {
        user_identity: userIdentity,
        user_name: '用户',
        metadata: { client: 'simple-voice-client' },
      }

      // 如果有开场白，添加到请求中
      if (presetMessage) {
        requestBody.preset_message = presetMessage
      }

      const response = await fetch(
        `${CONFIG.API_BASE_URL}/deployments/${encodeURIComponent(CONFIG.DEPLOYMENT_SLUG)}/sessions`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(requestBody),
        }
      )

      if (!response.ok) {
        const text = await response.text()
        throw new Error(`创建会话失败: ${response.status} ${text}`)
      }

      const data = await response.json()
      setSessionInfo({
        token: data.room_token,
        url: data.livekit_url,
        sessionId: data.session_id,
      })
    } catch (err) {
      console.error('创建会话错误:', err)
      setError(err instanceof Error ? err.message : '创建会话失败')
    } finally {
      setConnecting(false)
    }
  }, [])

  // 开发者弹窗状态
  const [devModal, setDevModal] = useState<{
    title: string
    steps: { icon: string; action: string; detail: string }[]
  } | null>(null)

  // 模拟外卖送达通知 - 只通知机器人，不开启会话
  const simulateDeliveryArrived = useCallback(() => {
    console.log('📦 检测到外卖送达通知，通知机器人去取外卖...')

    setDevModal({
      title: '📦 外卖已送达 - 流程演示',
      steps: [
        {
          icon: '1️⃣',
          action: 'NotificationMonitor 检测到送达通知',
          detail: `archives/notification-service → NotificationMonitor(keywords=["送达"])`,
        },
        {
          icon: '2️⃣',
          action: '通过 WebSocket 通知机器人取餐',
          detail: `# WebSocket 连接: ws://robot-server:8080/ws
ws.send(JSON.stringify({
  type: "command",
  action: "pick_up_delivery",
  payload: {
    location: "门口取餐柜",
    notification: "您的外卖已送达"
  }
}))`,
        },
        {
          icon: '3️⃣',
          action: '机器人接收指令并执行',
          detail: `机器人收到 WebSocket 消息后，自主导航至取餐点取外卖`,
        },
      ],
    })
  }, [])

  // 模拟外卖已取来 - 机器人取完后，主动开启会话通知用户
  const simulateDeliveryPickedUp = useCallback(() => {
    console.log('🍜 机器人已取回外卖，主动开启会话通知用户...')
    startSession('外卖已经取来了，趁热吃吧！')
  }, [startSession])

  const handleRestart = useCallback(() => {
    setSessionInfo(null)
    startSession(undefined)
  }, [startSession])

  return (
    <div style={styles.appContainer}>
      <div style={styles.card}>
        {/* 标题 */}
        <div style={styles.header}>
          <h1 style={styles.title}>🎙️ 语音助手</h1>
          <p style={styles.subtitle}>与 AI 助手进行语音对话</p>
        </div>

        {/* 内容区 */}
        <div style={styles.content}>
          {/* 错误提示 */}
          {error && (
            <div style={styles.errorBox}>
              ❌ {error}
              <button onClick={() => setError(null)} style={styles.dismissButton}>✕</button>
            </div>
          )}

          {/* 连接中 */}
          {connecting && (
            <div style={styles.loadingBox}>
              <div style={styles.spinner} />
              <p>正在连接...</p>
            </div>
          )}

          {/* 已连接 */}
          {sessionInfo && (
            <LiveKitRoom
              token={sessionInfo.token}
              serverUrl={sessionInfo.url}
              connect={true}
              audio={true}
              video={false}
              onDisconnected={() => console.log('已断开连接')}
              options={{
                // 禁用浏览器音频输出，只通过机器人播放
                audioCaptureDefaults: { echoCancellation: true, noiseSuppression: true },
                publishDefaults: { audioPreset: undefined },
              }}
            >
              <AgentSessionUI onRestart={handleRestart} />
              {/* 使用机器人扬声器播放，不在浏览器播放音频 */}
              <RobotTTSBridge />
              {/* <RoomAudioRenderer /> - 已禁用，改用机器人播放 */}
              {/* 添加禁音组件来阻止自动播放 */}
              <DisableAudioOutput />
            </LiveKitRoom>
          )}

          {/* 未连接 */}
          {!sessionInfo && !connecting && !error && (
            <div style={styles.startContainer}>
              <div style={{ fontSize: '64px', marginBottom: '24px' }}>🎤</div>
              <button onClick={() => startSession(undefined)} style={styles.startButton}>
                开始对话
              </button>
              <p style={styles.startHint}>点击按钮开始与 AI 助手交流</p>

              {/* 模拟按钮区 */}
              <div style={styles.simulateSection}>
                <div style={styles.simulateTitle}>🧪 模拟场景</div>
                <div style={styles.simulateButtons}>
                  <button onClick={simulateDeliveryArrived} style={styles.simulateButton}>
                    📦 外卖已送达
                    <span style={styles.simulateDesc}>通知机器人取餐</span>
                  </button>
                  <button onClick={simulateDeliveryPickedUp} style={styles.simulateButton}>
                    🍜 外卖已取来
                    <span style={styles.simulateDesc}>主动开启会话</span>
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* 底部提示 */}
        <div style={styles.footer}>
          💡 请确保浏览器已授权麦克风权限
        </div>
      </div>

      {/* 开发者弹窗 */}
      {devModal && (
        <div style={styles.modalOverlay} onClick={() => setDevModal(null)}>
          <div style={styles.modalContent} onClick={e => e.stopPropagation()}>
            <div style={styles.modalHeader}>
              <span style={styles.modalTitle}>{devModal.title}</span>
              <button style={styles.modalClose} onClick={() => setDevModal(null)}>✕</button>
            </div>
            <div style={styles.modalBody}>
              {devModal.steps.map((step, index) => (
                <div key={index} style={styles.stepItem}>
                  <div style={styles.stepHeader}>
                    <span style={styles.stepIcon}>{step.icon}</span>
                    <span style={styles.stepAction}>{step.action}</span>
                  </div>
                  <div style={styles.stepDetail}>
                    <code>{step.detail}</code>
                  </div>
                </div>
              ))}
            </div>
            <div style={styles.modalFooter}>
              <span style={{ color: 'rgba(255,255,255,0.4)', fontSize: '12px' }}>
                * 此为开发演示，实际接口调用需根据项目实现
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ========== 样式 ==========
const styles: Record<string, React.CSSProperties> = {
  appContainer: {
    padding: '20px',
    width: '100%',
    maxWidth: '900px',
  },
  card: {
    background: 'rgba(255, 255, 255, 0.03)',
    backdropFilter: 'blur(20px)',
    borderRadius: '24px',
    border: '1px solid rgba(255, 255, 255, 0.08)',
    padding: '32px',
    boxShadow: '0 8px 32px rgba(0, 0, 0, 0.4)',
  },
  header: {
    textAlign: 'center',
    marginBottom: '24px',
    paddingBottom: '24px',
    borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
  },
  title: {
    fontSize: '28px',
    fontWeight: 700,
    marginBottom: '8px',
    background: 'linear-gradient(90deg, #60a5fa, #a78bfa)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
  },
  subtitle: {
    fontSize: '14px',
    color: 'rgba(255, 255, 255, 0.5)',
  },
  content: {
    minHeight: '450px',
  },
  sessionContainer: {
    display: 'flex',
    flexDirection: 'column',
  },
  mainContent: {
    display: 'flex',
    gap: '24px',
    height: '380px',
  },
  leftPanel: {
    flex: 1,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'rgba(0, 0, 0, 0.2)',
    borderRadius: '16px',
    border: '1px solid rgba(255, 255, 255, 0.05)',
    height: '100%',
  },
  rightPanel: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    background: 'rgba(0, 0, 0, 0.2)',
    borderRadius: '16px',
    border: '1px solid rgba(255, 255, 255, 0.05)',
    overflow: 'hidden',
    height: '100%',
  },
  transcriptHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '16px 20px',
    borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
    fontSize: '14px',
    fontWeight: 600,
    color: 'rgba(255, 255, 255, 0.8)',
  },
  transcriptContainer: {
    flex: 1,
    overflowY: 'auto',
    padding: '16px 20px',
  },
  emptyTranscript: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    height: '100%',
    color: 'rgba(255, 255, 255, 0.3)',
    fontSize: '14px',
    textAlign: 'center',
  },
  voiceContainer: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '24px',
    padding: '40px',
  },
  visualizerWrapper: {
    width: '180px',
    height: '100px',
  },
  stateIndicator: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    fontSize: '20px',
    fontWeight: 600,
  },
  stateDot: {
    width: '12px',
    height: '12px',
    borderRadius: '50%',
    animation: 'pulse 1.5s ease-in-out infinite',
  },
  hint: {
    fontSize: '13px',
    color: 'rgba(255, 255, 255, 0.4)',
  },
  controlPanel: {
    display: 'flex',
    justifyContent: 'center',
    gap: '12px',
    marginTop: '20px',
    paddingTop: '20px',
    borderTop: '1px solid rgba(255, 255, 255, 0.08)',
  },
  controlButton: {
    padding: '10px 20px',
    fontSize: '14px',
    fontWeight: 500,
    color: 'rgba(255, 255, 255, 0.8)',
    background: 'rgba(255, 255, 255, 0.08)',
    border: '1px solid rgba(255, 255, 255, 0.12)',
    borderRadius: '10px',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
  startContainer: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    height: '100%',
    minHeight: '400px',
  },
  startButton: {
    padding: '18px 56px',
    fontSize: '18px',
    fontWeight: 600,
    color: '#fff',
    background: 'linear-gradient(135deg, #3b82f6, #8b5cf6)',
    border: 'none',
    borderRadius: '50px',
    cursor: 'pointer',
    transition: 'all 0.3s ease',
    boxShadow: '0 4px 24px rgba(59, 130, 246, 0.4)',
  },
  startHint: {
    marginTop: '16px',
    fontSize: '14px',
    color: 'rgba(255, 255, 255, 0.4)',
  },
  simulateSection: {
    marginTop: '48px',
    paddingTop: '32px',
    borderTop: '1px solid rgba(255, 255, 255, 0.1)',
    width: '100%',
    textAlign: 'center',
  },
  simulateTitle: {
    fontSize: '14px',
    color: 'rgba(255, 255, 255, 0.5)',
    marginBottom: '16px',
  },
  simulateButtons: {
    display: 'flex',
    gap: '12px',
    justifyContent: 'center',
    flexWrap: 'wrap',
  },
  simulateButton: {
    padding: '16px 24px',
    fontSize: '14px',
    fontWeight: 500,
    color: 'rgba(255, 255, 255, 0.8)',
    background: 'rgba(255, 255, 255, 0.08)',
    border: '1px solid rgba(255, 255, 255, 0.15)',
    borderRadius: '12px',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '6px',
    minWidth: '140px',
  },
  simulateDesc: {
    fontSize: '11px',
    color: 'rgba(255, 255, 255, 0.4)',
    fontWeight: 400,
  },
  modalOverlay: {
    position: 'fixed',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    background: 'rgba(0, 0, 0, 0.7)',
    backdropFilter: 'blur(4px)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1000,
    animation: 'fadeIn 0.2s ease',
  },
  modalContent: {
    background: 'linear-gradient(135deg, #1e293b 0%, #0f172a 100%)',
    borderRadius: '16px',
    border: '1px solid rgba(255, 255, 255, 0.1)',
    width: '90%',
    maxWidth: '520px',
    boxShadow: '0 20px 60px rgba(0, 0, 0, 0.5)',
    animation: 'slideUp 0.3s ease',
  },
  modalHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '20px 24px',
    borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
  },
  modalTitle: {
    fontSize: '18px',
    fontWeight: 600,
    color: '#fff',
  },
  modalClose: {
    background: 'none',
    border: 'none',
    color: 'rgba(255, 255, 255, 0.5)',
    fontSize: '18px',
    cursor: 'pointer',
    padding: '4px 8px',
    borderRadius: '4px',
    transition: 'all 0.2s',
  },
  modalBody: {
    padding: '24px',
    display: 'flex',
    flexDirection: 'column',
    gap: '20px',
  },
  stepItem: {
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
  },
  stepHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
  },
  stepIcon: {
    fontSize: '16px',
  },
  stepAction: {
    fontSize: '15px',
    fontWeight: 600,
    color: '#60a5fa',
  },
  stepDetail: {
    background: 'rgba(0, 0, 0, 0.3)',
    borderRadius: '8px',
    padding: '12px 16px',
    fontSize: '12px',
    fontFamily: 'Monaco, Consolas, monospace',
    color: '#94a3b8',
    overflowX: 'auto',
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-all',
  },
  modalFooter: {
    padding: '16px 24px',
    borderTop: '1px solid rgba(255, 255, 255, 0.1)',
    textAlign: 'center',
  },
  loadingBox: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    height: '100%',
    minHeight: '400px',
    gap: '16px',
    color: 'rgba(255, 255, 255, 0.8)',
  },
  spinner: {
    width: '48px',
    height: '48px',
    border: '3px solid rgba(255, 255, 255, 0.1)',
    borderTopColor: '#60a5fa',
    borderRadius: '50%',
    animation: 'spin 1s linear infinite',
  },
  errorBox: {
    padding: '16px 20px',
    background: 'rgba(239, 68, 68, 0.15)',
    border: '1px solid rgba(239, 68, 68, 0.25)',
    borderRadius: '12px',
    color: '#fca5a5',
    fontSize: '14px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: '20px',
  },
  dismissButton: {
    background: 'none',
    border: 'none',
    color: '#fca5a5',
    cursor: 'pointer',
    padding: '4px 8px',
    fontSize: '16px',
  },
  footer: {
    marginTop: '24px',
    paddingTop: '20px',
    borderTop: '1px solid rgba(255, 255, 255, 0.08)',
    textAlign: 'center',
    fontSize: '12px',
    color: 'rgba(255, 255, 255, 0.35)',
  },
}

// CSS 动画
const styleSheet = document.createElement('style')
styleSheet.textContent = `
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }
  @keyframes slideIn {
    from {
      opacity: 0;
      transform: translateY(-10px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
  @keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
  }
  @keyframes slideUp {
    from {
      opacity: 0;
      transform: translateY(20px) scale(0.95);
    }
    to {
      opacity: 1;
      transform: translateY(0) scale(1);
    }
  }
  button:hover {
    transform: translateY(-2px);
    filter: brightness(1.1);
  }
  button:active {
    transform: translateY(0);
  }
  ::-webkit-scrollbar {
    width: 6px;
  }
  ::-webkit-scrollbar-track {
    background: transparent;
  }
  ::-webkit-scrollbar-thumb {
    background: rgba(255, 255, 255, 0.2);
    border-radius: 3px;
  }
  ::-webkit-scrollbar-thumb:hover {
    background: rgba(255, 255, 255, 0.3);
  }
`
document.head.appendChild(styleSheet)
