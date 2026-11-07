import {useCallback, useEffect, useRef, useState} from 'react'
import {callRpc} from '../api'
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
    const sendingRef = useRef(new Set())
    const unacknowledgedMessagesRef = useRef(new Map())
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
            if (!message?.chat_uuid) return
            const messageChatUuid = message.chat_uuid

            if (message.type === 'message' || message.type === 'tool_call') {
                setMessages((messages) => {
                    const existingMessageIndex = messages.findIndex((existingMessage) => existingMessage.uuid === message.uuid)

                    if (existingMessageIndex === -1) {
                        return [...messages, message]
                    }

                    if ((messages[existingMessageIndex].revision ?? 0) > (message.revision ?? 0)) return messages
                    return messages.map((existingMessage) => (existingMessage.uuid === message.uuid ? message : existingMessage))
                }, messageChatUuid)

                if (messageChatUuid === activeChatRef.current?.uuid && userInteractionTriggerRef.current) {
                    setNeedToScrollChat(true)
                }
            } else if (message.type === 'action') {
                if (message.name === 'set_chat_status') {
                    await updateMessengerState({
                        ...message.payload,
                        revision: message.revision,
                        chatUuid: messageChatUuid,
                    })
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
        const message = inputValue.trim()
        const chatUuid = activeChat?.uuid
        if (!chatUuid) {
            await addNotification('Open a chat before sending a message.')
            return
        }
        if (
            (!message && attachedFiles.length === 0) ||
            sendingRef.current.has(chatUuid) ||
            chatState.status === 'loading' ||
            document.getElementById('send-btn')?.disabled
        )
            return

        const body = {content: message, attachments: attachedFiles.map((file) => file.id)}
        const previousAttempt = unacknowledgedMessagesRef.current.get(chatUuid)
        // A lost acknowledgement is not proof of rejection. Reuse the UUID for
        // an unchanged retry so the backend can acknowledge it without rerunning tools.
        const preparedMessage =
            previousAttempt && JSON.stringify(previousAttempt.body) === JSON.stringify(body)
                ? previousAttempt
                : {
                      uuid: uuid.v4(),
                      chat_uuid: chatUuid,
                      from: 'user',
                      body,
                      // Sent messages use durable upload URLs, not draft-owned blob previews.
                      attachments: attachedFiles.map(({id, name, url}) => ({id, name, url})),
                  }
        unacknowledgedMessagesRef.current.set(chatUuid, preparedMessage)
        sendingRef.current.add(chatUuid)
        setChatWaiting(chatUuid, true)
        setInputValue('')
        updateMessengerState({status: 'loading', text: null, chatUuid})
        setMessages(
            (messages) => (messages.some((item) => item.uuid === preparedMessage.uuid) ? messages : [...messages, preparedMessage]),
            chatUuid
        )
        userInteractionTriggerRef.current = true
        setNeedToScrollChat(true)

        try {
            const acknowledgement = await callRpc('process_message', [preparedMessage])
            if (!acknowledgement?.accepted) throw new Error('The server did not accept this message.')
            unacknowledgedMessagesRef.current.delete(chatUuid)
            if (activeChatRef.current?.uuid === chatUuid) clearFiles()
            if (acknowledgement.duplicate) {
                updateMessengerState({...acknowledgement, chatUuid})
            }
        } catch (error) {
            // Keep the draft and attachments on failure instead of silently discarding them.
            setMessages((messages) => messages.filter((item) => item.uuid !== preparedMessage.uuid), chatUuid)
            if (activeChatRef.current?.uuid === chatUuid) {
                setInputValue((current) => (current ? `${message}\n\n${current}` : message))
            }
            updateMessengerState({status: 'idle', text: null, chatUuid})
            await processRpcError(error)
            if (window.rpcClient.ready) window.dispatchEvent(new Event('rpc-connection'))
        } finally {
            sendingRef.current.delete(chatUuid)
            userInteractionTriggerRef.current = false
            setChatWaiting(chatUuid, false)
            textareaRef.current?.focus()
        }
    }, [
        activeChat,
        addNotification,
        inputValue,
        attachedFiles,
        chatState.status,
        setChatWaiting,
        updateMessengerState,
        setMessages,
        clearFiles,
        processRpcError,
        textareaRef,
    ])

    const deleteMessage = useCallback(
        async (messageUuid) => {
            console.log(`deleteMessage ${messageUuid}`)
            const chatUuid = activeChat?.uuid

            if (!chatUuid) {
                return
            }

            try {
                setChatWaiting(chatUuid, true)
                await callRpc('delete_message', [messageUuid])
                setMessages((messages) => messages.filter((message) => message.uuid !== messageUuid), chatUuid)
            } catch (error) {
                await processRpcError(error)
            } finally {
                setChatWaiting(chatUuid, false)
            }
        },
        [setMessages, setChatWaiting, processRpcError, activeChat]
    )

    const callButtonCallback = useCallback(
        async (callbackPayload) => {
            const chatUuid = activeChat?.uuid
            if (!chatUuid || sendingRef.current.has(chatUuid)) return
            sendingRef.current.add(chatUuid)
            const wasLoading = chatState.status === 'loading'
            if (!wasLoading) updateMessengerState({status: 'loading', chatUuid})
            try {
                await callRpc('process_message', [
                    {
                        uuid: uuid.v4(),
                        chat_uuid: chatUuid,
                        from: 'user',
                        body: {callback: callbackPayload},
                    },
                ])
            } catch (error) {
                if (!wasLoading) updateMessengerState({status: 'idle', chatUuid})
                await processRpcError(error)
                if (window.rpcClient.ready) window.dispatchEvent(new Event('rpc-connection'))
            } finally {
                sendingRef.current.delete(chatUuid)
            }
        },
        [activeChat, chatState.status, updateMessengerState, processRpcError]
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
            if (
                event.key === 'Enter' &&
                !event.isComposing &&
                (event.metaKey || event.ctrlKey) &&
                !document.getElementById('send-btn')?.disabled
            ) {
                event.preventDefault()
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
