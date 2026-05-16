import {useCallback, useEffect} from 'react'

function useChat({
    updateMessengerState,
    setMessages,
    removeChatMessages,
    clearFiles,
    getSettings,
    processRpcError,
    activeChat,
    setActiveChat,
}) {
    const getHistory = useCallback(async () => {
        if (activeChat) {
            const rpcClient = window.rpcClient
            const history = await rpcClient.call('get_history', [activeChat.uuid]).catch(processRpcError)
            console.log('History:', history)
            setMessages(history ?? [], activeChat.uuid)
        }
    }, [setMessages, processRpcError, activeChat])

    const openChat = useCallback(
        async (chatName) => {
            const rpcClient = window.rpcClient
            await updateMessengerState({status: 'loading', text: null})
            await clearFiles()
            await rpcClient.call('open_chat', [chatName]).catch(processRpcError)
            await getSettings({
                callback: (newSettings) => {
                    const openedChats = newSettings?.opened_chats ?? []
                    setActiveChat(openedChats[openedChats.length - 1] ?? null)
                },
            })
            await updateMessengerState({status: 'idle', text: null})
        },
        [updateMessengerState, getSettings, clearFiles, processRpcError, setActiveChat]
    )

    const closeChat = useCallback(
        async (chatUuid) => {
            const rpcClient = window.rpcClient
            await updateMessengerState({status: 'loading', text: null, chatUuid})
            await clearFiles()
            await rpcClient.call('close_chat', [chatUuid]).catch(processRpcError)
            removeChatMessages(chatUuid)
            await getSettings({
                callback: (newSettings) => {
                    const openedChats = newSettings?.opened_chats ?? []

                    if (activeChat?.uuid === chatUuid) {
                        setActiveChat(openedChats[0] ?? null)
                    }
                },
            })
            await updateMessengerState({status: 'idle', text: null, chatUuid})
        },
        [updateMessengerState, clearFiles, getSettings, processRpcError, activeChat, setActiveChat, removeChatMessages]
    )

    const clearChat = useCallback(
        async (chatUuid) => {
            const rpcClient = window.rpcClient
            setMessages([], chatUuid)
            await clearFiles()
            await rpcClient.call('clear_chat', [chatUuid]).catch(processRpcError)
        },
        [setMessages, clearFiles, processRpcError]
    )

    useEffect(() => {
        getHistory()
    }, [getHistory])

    return {openChat, closeChat, clearChat}
}

export default useChat
