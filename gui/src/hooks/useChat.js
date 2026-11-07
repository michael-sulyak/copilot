import {useCallback, useEffect, useRef} from 'react'
import {callRpc, subscribeConnection} from '../api'

function useChat({
    updateMessengerState,
    setMessages,
    removeChatMessages,
    clearFiles,
    settings,
    getSettings,
    processRpcError,
    activeChat,
    setActiveChat,
}) {
    const historyRequestRef = useRef(0)
    const chatUuid = activeChat?.uuid

    useEffect(() => {
        let disposed = false
        const refresh = async () => {
            if (!chatUuid || !window.rpcClient.ready) return
            const requestId = ++historyRequestRef.current
            const pendingEvents = []
            const collect = ([event]) => {
                if (event?.chat_uuid === chatUuid) pendingEvents.push(event)
            }
            const client = window.rpcClient
            client.on('process_message', collect)
            try {
                const snapshot = await callRpc('get_chat_state', [chatUuid])
                if (disposed || requestId !== historyRequestRef.current) return
                const history = new Map(snapshot.history.map((message) => [message.uuid, message]))
                let state = {status: snapshot.status, text: snapshot.text, revision: snapshot.revision}
                // Notifications can arrive while the snapshot RPC is in flight.
                for (const event of pendingEvents) {
                    if (event.revision <= snapshot.revision) continue
                    if (event.type === 'message' || event.type === 'tool_call') history.set(event.uuid, event)
                    if (event.type === 'action' && event.name === 'set_chat_status') state = {...event.payload, revision: event.revision}
                }
                setMessages((previous) => {
                    // A user may send while the snapshot is in flight. Keep
                    // optimistic user messages not yet included in that snapshot.
                    const merged = new Map(history)
                    for (const message of previous) {
                        if (message.from === 'user' && !merged.has(message.uuid)) merged.set(message.uuid, message)
                    }
                    return [...merged.values()]
                }, chatUuid)
                updateMessengerState({...state, chatUuid})
            } catch (error) {
                if (!disposed) processRpcError(error)
            } finally {
                client.off('process_message', collect)
            }
        }
        refresh()
        const unsubscribe = subscribeConnection(refresh)
        return () => {
            disposed = true
            unsubscribe()
        }
    }, [chatUuid, settings, setMessages, updateMessengerState, processRpcError])

    const openChat = useCallback(
        async (chatName) => {
            try {
                const chat = await callRpc('open_chat', [chatName])
                clearFiles()
                await getSettings({callback: () => setActiveChat(chat)})
            } catch (error) {
                await processRpcError(error)
            }
        },
        [clearFiles, getSettings, setActiveChat, processRpcError]
    )

    const closeChat = useCallback(
        async (targetUuid) => {
            const activeIndex = Math.max(
                0,
                (settings.opened_chats ?? []).findIndex((chat) => chat.uuid === activeChat?.uuid)
            )
            try {
                await callRpc('close_chat', [targetUuid], 60000)
                historyRequestRef.current += 1
                removeChatMessages(targetUuid)
                if (activeChat?.uuid === targetUuid) clearFiles()
                await getSettings({
                    callback: (next) => {
                        if (activeChat?.uuid === targetUuid) {
                            setActiveChat(next.opened_chats[Math.min(next.opened_chats.length - 1, activeIndex)] ?? null)
                        }
                    },
                })
                return true
            } catch (error) {
                await processRpcError(error)
                return false
            }
        },
        [settings, activeChat, removeChatMessages, clearFiles, getSettings, setActiveChat, processRpcError]
    )

    const clearChat = useCallback(
        async (targetUuid) => {
            try {
                const snapshot = await callRpc('clear_chat', [targetUuid], 60000)
                historyRequestRef.current += 1
                setMessages(snapshot.history, targetUuid)
                clearFiles()
                updateMessengerState({...snapshot, chatUuid: targetUuid})
            } catch (error) {
                await processRpcError(error)
            }
        },
        [setMessages, clearFiles, updateMessengerState, processRpcError]
    )

    return {openChat, closeChat, clearChat}
}

export default useChat
