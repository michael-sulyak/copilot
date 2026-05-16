import React, {Fragment, useCallback, useEffect, useMemo, useRef, useState} from 'react'
import {Card, ToastContainer} from 'react-bootstrap'
import Header from './components/Header'
import Message from './components/Message'
import Footer from './components/Footer'
import Notification from './components/Notification'
import useNotifications from './hooks/useNotifications'
import useSettings from './hooks/useSettings'
import useMessengerState from './hooks/useMessengerState'
import useFileUpload from './hooks/useFileUpload'
import useAudioRecording from './hooks/useAudioRecording'
import useChat from './hooks/useChat'
import useInput from './hooks/useInput'
import ChatTabs from './components/ChatTabs'
import useActiveChat from './hooks/useActiveChat'

function Messenger() {
    const chatBodyRef = useRef(null)
    const textareaRef = useRef(null)
    const fileInputRef = useRef(null)
    const [messagesByChatUuid, setMessagesByChatUuid] = useState({})
    const {notifications, addNotification, removeNotification} = useNotifications()
    useEffect(() => {
        const rpcClient = window.rpcClient

        const handleShowNotification = (message) => {
            addNotification(message)
        }

        rpcClient.on('show_notification', handleShowNotification)

        return () => {
            rpcClient.off('show_notification', handleShowNotification)
        }
    }, [addNotification])
    const processRpcError = useCallback(
        async (response) => {
            console.error(response)
            await addNotification(`**${response.message}**\n\n${response?.data?.traceback_exception?.slice(-2)}\n\n(See logs)`)
        },
        [addNotification]
    )
    const {settings, getSettings} = useSettings({addNotification, processRpcError})
    const {activeChat, setActiveChat} = useActiveChat({settings})
    const activeChatUuid = activeChat?.uuid ?? null
    const messages = useMemo(() => (activeChatUuid ? (messagesByChatUuid[activeChatUuid] ?? []) : []), [activeChatUuid, messagesByChatUuid])
    const setMessages = useCallback(
        (updater, chatUuid = activeChatUuid) => {
            if (!chatUuid) {
                return
            }

            setMessagesByChatUuid((prevMessagesByChatUuid) => {
                const previousMessages = prevMessagesByChatUuid[chatUuid] ?? []
                const nextMessages = typeof updater === 'function' ? updater(previousMessages) : updater

                return {
                    ...prevMessagesByChatUuid,
                    [chatUuid]: nextMessages ?? [],
                }
            })
        },
        [activeChatUuid]
    )
    const removeChatMessages = useCallback((chatUuid) => {
        setMessagesByChatUuid((prevMessagesByChatUuid) => {
            if (!prevMessagesByChatUuid[chatUuid]) {
                return prevMessagesByChatUuid
            }

            const nextMessagesByChatUuid = {...prevMessagesByChatUuid}
            delete nextMessagesByChatUuid[chatUuid]
            return nextMessagesByChatUuid
        })
    }, [])
    const {chatState, updateMessengerState} = useMessengerState({activeChatUuid})
    const {attachedFiles, onFileUpload, removeAttachedFile, clearFiles, uploadFiles} = useFileUpload({
        addNotification,
        updateMessengerState,
    })
    const {inputValue, setInputValue, sendMessage, deleteMessage, callButtonCallback, isWaitingAnswer, handleInputChange} = useInput({
        textareaRef,
        addNotification,
        attachedFiles,
        clearFiles,
        chatState,
        updateMessengerState,
        chatBodyRef,
        setMessages,
        processRpcError,
        activeChat,
    })
    const {recordingState, startRecording, stopRecording} = useAudioRecording({
        addNotification,
        inputValue,
        setInputValue,
        chatState,
        uploadFiles,
        updateMessengerState,
        processRpcError,
    })
    const {openChat, closeChat, clearChat} = useChat({
        updateMessengerState,
        setMessages,
        removeChatMessages,
        clearFiles,
        getSettings,
        processRpcError,
        activeChat,
        setActiveChat,
    })

    const clearActiveChat = () => activeChat && clearChat(activeChat.uuid)

    return (
        <Card className="chat-card border-0 h-100 d-flex flex-column">
            <Header settings={settings} clearChat={clearActiveChat} insertText={setInputValue} />

            <ChatTabs settings={settings} openChat={openChat} closeChat={closeChat} activeChat={activeChat} setActiveChat={setActiveChat} />

            <Card.Body className="chat-body" ref={chatBodyRef}>
                <div className="chat-body-shadow"></div>
                {messages.map((message) => (
                    <Message
                        key={message.uuid}
                        message={message}
                        addNotification={addNotification}
                        deleteMessage={deleteMessage}
                        callButtonCallback={callButtonCallback}
                    />
                ))}
            </Card.Body>

            <Footer
                handleInputChange={handleInputChange}
                inputValue={inputValue}
                textareaRef={textareaRef}
                isLoading={!activeChat || isWaitingAnswer || chatState.status === 'loading'}
                activeChat={activeChat}
                onFileUpload={onFileUpload}
                fileInputRef={fileInputRef}
                attachedFiles={attachedFiles}
                sendMessage={sendMessage}
                removeAttachedFile={removeAttachedFile}
                chatState={chatState}
                recordingState={recordingState}
                startRecording={startRecording}
                stopRecording={stopRecording}
            />

            <ToastContainer position="top-center" className="position-fixed">
                {notifications.map((notification) => (
                    <Fragment key={notification.id}>
                        <Notification notification={notification} onHide={() => removeNotification(notification.id)} />
                    </Fragment>
                ))}
            </ToastContainer>
        </Card>
    )
}

export default Messenger
