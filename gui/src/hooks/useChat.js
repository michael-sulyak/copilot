import {useCallback, useEffect} from 'react'

function useChat({updateMessangerState, setMessages, clearFiles, settings, getSettings, processRpcError, activeChat, setActiveChat}) {
    const getHistory = useCallback(async () => {
        if (activeChat) {
            const rpcClient = window.rpcClient
            const history = await rpcClient.call('get_history', [activeChat.uuid]).catch(processRpcError)
            console.log('History:', history)
            setMessages(history)
        }
    }, [setMessages, processRpcError, activeChat])

    const openChat = useCallback(
        async (chatName) => {
            const rpcClient = window.rpcClient
            await updateMessangerState({status: 'loading', text: null})
            await setMessages([])
            await clearFiles()
            await rpcClient.call('open_chat', [chatName]).catch(processRpcError)
            await getSettings({callback: (newSettings) => setActiveChat(newSettings.opened_chats && newSettings.opened_chats[newSettings.opened_chats.length - 1])})
            await updateMessangerState({status: 'idle', text: null})
        },
        [updateMessangerState, setMessages, getSettings, getHistory, clearFiles, processRpcError, setActiveChat]
    )

    const closeChat = useCallback(
        async (chat_uuid) => {
            const rpcClient = window.rpcClient
            await updateMessangerState({status: 'loading', text: null})
            await setMessages([])
            await clearFiles()
            await rpcClient.call('close_chat', [chat_uuid]).catch(processRpcError)
            await getSettings({})
            await updateMessangerState({status: 'idle', text: null})
        },
        [updateMessangerState, setMessages, clearFiles, getSettings, getHistory, processRpcError]
    )

    const clearChat = useCallback(async (chat_uuid) => {
        const rpcClient = window.rpcClient
        await setMessages([])
        await clearFiles()
        await rpcClient.call('clear_chat', [chat_uuid])
    }, [setMessages, clearFiles])

    useEffect(() => {
        getHistory()
    }, [getHistory])

    return {openChat, closeChat, clearChat}
}

export default useChat