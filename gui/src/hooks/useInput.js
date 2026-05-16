import {useCallback, useEffect, useRef, useState} from 'react'
import {needToTurnOnVPN} from '../utils'
import * as uuid from 'uuid'

function useChatState({
    textareaRef,
    chatBodyRef,
    addNotification,
    attachedFiles,
    clearFiles,
    chatState,
    updateMessengerState,
    setMessages,
    processRpcError,
    activeChat,
}) {
    const [inputValue, setInputValue] = useState('')
    const [waitingByChatUuid, setWaitingByChatUuid] = useState({})
    const userInteractionTriggerRef = useRef(false)
    const activeChatRef = useRef(activeChat)
    const [needToScrollChat, setNeedToScrollChat] = useState(null)
    const activeChatUuid = activeChat?.uuid ?? null
    const isWaitingAnswer = activeChatUuid ? !!waitingByChatUuid[activeChatUuid] : false

    useEffect(() => {
        activeChatRef.current = activeChat
    }, [activeChat])

    const setChatWaiting = useCallback((chatUuid, isWaiting) => {
        setWaitingByChatUuid((prevWaitingByChatUuid) => ({
            ...prevWaitingByChatUuid,
            [chatUuid]: isWaiting,
        }))
    }, [])

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
        if (!textareaRef.current || !chatBodyRef.current) {
            return
        }

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
        const handleProcessMessage = async ([message]) => {
            const messageChatUuid = message.chat_uuid

            if (message.type === 'message') {
                setMessages((messages) => [...messages, message], messageChatUuid)

                if (messageChatUuid === activeChatRef.current?.uuid && userInteractionTriggerRef.current) {
                    userInteractionTriggerRef.current = false
                    setNeedToScrollChat(true)
                }
            } else if (message.type === 'action') {
                if (message.name === 'set_chat_status') {
                    await updateMessengerState({...message.payload, chatUuid: messageChatUuid})
                }
            }
        }

        rpcClient.on('process_message', handleProcessMessage)

        return () => {
            rpcClient.off('process_message', handleProcessMessage)
        }
    }, [setNeedToScrollChat, updateMessengerState, setMessages])

    useEffect(() => {
        updateTextareaHeight()
    }, [inputValue, updateTextareaHeight])

    const sendMessage = useCallback(async () => {
        console.log('sendMessage')
        const rpcClient = window.rpcClient
        const message = inputValue.trim()
        const chatUuid = activeChat?.uuid

        if (!chatUuid) {
            await addNotification('Open a chat before sending a message.')
            return
        }

        if (!message) {
            return
        }

        setChatWaiting(chatUuid, true)
        setInputValue('')
        textareaRef.current?.focus()

        try {
            if (await needToTurnOnVPN({addNotification})) {
                await showMsgAboutVPN()
                setInputValue(message)
                return
            }

            const preparedMessage = {
                uuid: uuid.v4(),
                chat_uuid: chatUuid,
                from: 'user',
                body: {
                    content: message,
                    attachments: attachedFiles.map((attachedFile) => attachedFile.id),
                },
                __ui__: {
                    attachments: attachedFiles,
                },
            }

            setMessages((messages) => [...messages, preparedMessage], chatUuid)

            userInteractionTriggerRef.current = true
            setNeedToScrollChat(true)

            await rpcClient.call('process_message', [preparedMessage]).catch(processRpcError)

            await clearFiles()
        } finally {
            setChatWaiting(chatUuid, false)
        }
    }, [
        activeChat,
        processRpcError,
        setNeedToScrollChat,
        addNotification,
        textareaRef,
        inputValue,
        attachedFiles,
        showMsgAboutVPN,
        clearFiles,
        setMessages,
        setChatWaiting,
    ])

    const deleteMessage = useCallback(
        async (messageUuid) => {
            console.log(`deleteMessage ${messageUuid}`)
            const rpcClient = window.rpcClient
            const chatUuid = activeChat?.uuid

            if (!chatUuid) {
                return
            }

            try {
                setChatWaiting(chatUuid, true)
                await rpcClient.call('delete_message', [messageUuid]).catch(processRpcError)
                setMessages((messages) => messages.filter((message) => message.uuid !== messageUuid), chatUuid)
            } finally {
                setChatWaiting(chatUuid, false)
            }
        },
        [setMessages, setChatWaiting, processRpcError, activeChat]
    )

    const callButtonCallback = useCallback(
        async (callbackPayload) => {
            const rpcClient = window.rpcClient
            const chatUuid = activeChat?.uuid

            if (!chatUuid) {
                return
            }

            await updateMessengerState({status: 'loading', chatUuid})
            const preparedMessage = {uuid: uuid.v4(), chat_uuid: chatUuid, from: 'user', body: {callback: callbackPayload}}
            try {
                const response = await rpcClient.call('process_message', [preparedMessage]).catch(processRpcError)
                response && setMessages((prev) => [...prev, response], chatUuid)
            } catch (err) {
                addNotification('Error processing callback: ' + err)
            } finally {
                await updateMessengerState({status: 'idle', chatUuid})
            }
        },
        [processRpcError, setMessages, updateMessengerState, addNotification, activeChat]
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
        updateMessengerState,
        sendMessage,
        deleteMessage,
        callButtonCallback,
        isWaitingAnswer,
        handleInputChange,
    }
}

export default useChatState
