import {useCallback, useEffect, useState} from 'react'
import {needToTurnOnVPN} from '../utils'

function useChatState({
    textareaRef,
    chatBodyRef,
    addNotification,
    attachedFiles,
    clearFiles,
    chatState,
    updateChatState,
    setMessages,
    processRpcError,
}) {
    const [inputValue, setInputValue] = useState('')
    const [isWaitingAnswer, setIsWaitingAnswer] = useState(false)
    const [userInteractionTrigger, setUserInteractionTrigger] = useState(null)
    const [needToScrollChat, setNeedToScrollChat] = useState(null)
    const handleInputChange = useCallback(
        (event) => {
            setInputValue(event.target.value)
        },
        [setInputValue]
    )
    const showMsgAboutVPN = useCallback(async () => {
        await addNotification('You need to turn on VPN')
    }, [addNotification])
    const updateTextareaHeight = useCallback(() => {
        textareaRef.current.style.height = 'auto'
        const maxHeight = Math.max(200, window.screen.height * 0.1)
        let newHeight = textareaRef.current.scrollHeight + 2

        if (newHeight > maxHeight) {
            newHeight = maxHeight
        }

        textareaRef.current.style.height = `${newHeight}px`
        chatBodyRef.current.style.paddingBottom = `calc(${newHeight}px + 3rem)`
    }, [textareaRef, chatBodyRef])

    useEffect(() => {
        const rpcClient = window.rpcClient
        rpcClient.on('process_message', async ([message]) => {
            if (message.type === 'message') {
                await setMessages((messages) => [...messages, message])

                if (userInteractionTrigger) {
                    await setUserInteractionTrigger(false)
                    await setNeedToScrollChat(true)
                }
            } else if (message.type === 'action') {
                if (message.name === 'set_chat_status') {
                    await updateChatState(message.payload)
                }
            }
        })

        return () => {
            rpcClient.off('process_message')
        }
    }, [setNeedToScrollChat, updateChatState, userInteractionTrigger, chatState, setMessages, setUserInteractionTrigger, processRpcError])

    useEffect(() => {
        updateTextareaHeight()
    }, [inputValue, updateTextareaHeight])

    const sendMessage = useCallback(async () => {
        console.log('sendMessage')
        const rpcClient = window.rpcClient
        const message = inputValue.trim()

        if (!message) {
            return
        }

        await setIsWaitingAnswer(true)
        await setInputValue('')
        textareaRef.current.focus()

        if (await needToTurnOnVPN({addNotification})) {
            await showMsgAboutVPN()
            await setInputValue(message)
            await setIsWaitingAnswer(false)
            return
        }

        const preparedMessage = {
            from: 'user',
            body: {
                content: message,
                attachments: attachedFiles.map((attachedFile) => attachedFile.id),
            },
            __ui__: {
                attachments: attachedFiles,
            },
        }

        await setMessages((messages) => [...messages, preparedMessage])

        await setUserInteractionTrigger(true)
        await setNeedToScrollChat(true)

        await rpcClient.call('process_message', [preparedMessage]).catch(processRpcError)

        await clearFiles()
        await setIsWaitingAnswer(false)
    }, [
        processRpcError,
        setNeedToScrollChat,
        addNotification,
        textareaRef,
        inputValue,
        attachedFiles,
        showMsgAboutVPN,
        clearFiles,
        setUserInteractionTrigger,
        setMessages,
    ])

    const callButtonCallback = useCallback(
        async (callbackPayload) => {
            const rpcClient = window.rpcClient
            await updateChatState({status: 'loading'})
            const preparedMessage = {from: 'user', body: {callback: callbackPayload}}
            try {
                const response = await rpcClient.call('process_message', [preparedMessage]).catch(processRpcError)
                response && setMessages((prev) => [...prev, response])
            } catch (err) {
                addNotification('Error processing callback: ' + err)
            }
            await updateChatState({status: 'idle'})
        },
        [processRpcError, setMessages, updateChatState, addNotification]
    )

    useEffect(() => {
        if (textareaRef.current) {
            textareaRef.current.focus()
        }
    }, [textareaRef])

    useEffect(() => {
        if (needToScrollChat) {
            chatBodyRef.current?.lastElementChild?.scrollIntoView({
                behavior: 'smooth',
                block: 'start',
            })
            setNeedToScrollChat(false)
        }
    }, [chatBodyRef, needToScrollChat])

    useEffect(() => {
        const handleKeyPress = async (event) => {
            if (event.keyCode === 13 && (event.metaKey || event.ctrlKey)) {
                await sendMessage()
            }
        }
        document.addEventListener('keydown', handleKeyPress)
        return () => document.removeEventListener('keydown', handleKeyPress)
    }, [sendMessage])

    return {
        inputValue,
        setInputValue,
        chatState,
        updateChatState,
        sendMessage,
        callButtonCallback,
        isWaitingAnswer,
        setIsWaitingAnswer,
        handleInputChange,
    }
}

export default useChatState
