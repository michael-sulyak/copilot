import {useCallback, useEffect} from 'react'

function useDialog({updateChatState, setMessages, clearFiles, getSettings, processRpcError}) {
    const getHistory = useCallback(async () => {
        const rpcClient = window.rpcClient
        const history = await rpcClient.call('get_history', []).catch(processRpcError)
        console.log('History:')
        console.log(history)
        setMessages(history)
    }, [setMessages, processRpcError])

    const activateDialog = useCallback(
        async (dialogName) => {
            const rpcClient = window.rpcClient
            await updateChatState({status: 'loading', text: null})
            await setMessages([])
            await clearFiles()
            await rpcClient.call('activate_dialog', [dialogName]).catch(processRpcError)
            await getSettings()
            await updateChatState({status: 'idle', text: null})
        },
        [updateChatState, setMessages, getSettings, clearFiles, processRpcError]
    )

    const clearDialog = useCallback(async () => {
        const rpcClient = window.rpcClient
        await setMessages([])
        await clearFiles()
        await rpcClient.call('clear_dialog', [])
    }, [setMessages, clearFiles])

    useEffect(() => {
        getHistory()
    }, [getHistory])

    return {activateDialog, clearDialog}
}

export default useDialog
