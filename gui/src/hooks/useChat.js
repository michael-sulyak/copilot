import {useCallback, useEffect} from 'react'

function useChat({updateMessangerState, setMessages, clearFiles, getSettings, processRpcError}) {
    const getHistory = useCallback(async () => {
        const rpcClient = window.rpcClient
        const history = await rpcClient.call('get_history', []).catch(processRpcError)
        console.log('History:')
        console.log(history)
        setMessages(history)
    }, [setMessages, processRpcError])

    const openChat = useCallback(
        async (chatName) => {
            const rpcClient = window.rpcClient
            await updateMessangerState({status: 'loading', text: null})
            await setMessages([])
            await clearFiles()
            await rpcClient.call('open_chat', [chatName]).catch(processRpcError)
            await getSettings()
            await getHistory()
            await updateMessangerState({status: 'idle', text: null})
        },
        [updateMessangerState, setMessages, getSettings, getHistory, clearFiles, processRpcError]
    )

    const closeChat = useCallback(
        async (chatName) => {
            const rpcClient = window.rpcClient
            await updateMessangerState({status: 'loading', text: null})
            await setMessages([])
            await clearFiles()
            await rpcClient.call('close_chat', [chatName]).catch(processRpcError)
            await getSettings()
            await getHistory()
            await updateMessangerState({status: 'idle', text: null})
        },
        [updateMessangerState, setMessages, clearFiles, getSettings, getHistory, processRpcError]
    )

    const clearChat = useCallback(async () => {
        const rpcClient = window.rpcClient
        await setMessages([])
        await clearFiles()
        await rpcClient.call('clear_chat', [])
    }, [setMessages, clearFiles])

    useEffect(() => {
        getHistory()
    }, [getHistory])

    return {openChat, closeChat, clearChat}
}

export default useChat