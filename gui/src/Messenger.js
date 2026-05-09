import React, {Fragment, useCallback, useEffect, useRef, useState} from 'react'
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


function Messenger() {
    const chatBodyRef = useRef(null)
    const textareaRef = useRef(null)
    const fileInputRef = useRef(null)
    const [messages, setMessages] = useState([])
    const {notifications, addNotification, removeNotification} = useNotifications()
    useEffect(() => {
        const rpcClient = window.rpcClient

        rpcClient.on('show_notification', (message) => {
            addNotification(message)
        })

        return () => {
            rpcClient.off('show_notification')
        }
    }, [addNotification])
    const processRpcError = useCallback(
        async (response) => {
            console.error(response)
            await addNotification(`**${response.message}**\n\n${response?.data?.traceback_exception?.slice(-2)}\n\n(See logs)`)
        },
        [addNotification],
    )
    const {settings, getSettings} = useSettings({addNotification, processRpcError})
    const {chatState, updateMessangerState} = useMessengerState()
    const {attachedFiles, onFileUpload, removeAttachedFile, clearFiles, uploadFiles} = useFileUpload({
        addNotification,
        updateMessangerState,
    })
    const {
        inputValue,
        setInputValue,
        sendMessage,
        deleteMessage,
        callButtonCallback,
        isWaitingAnswer,
        handleInputChange,
    } = useInput({
        textareaRef,
        addNotification,
        attachedFiles,
        clearFiles,
        chatState,
        updateMessangerState,
        chatBodyRef,
        setMessages,
    })
    const {recordingState, startRecording, stopRecording} = useAudioRecording({
        addNotification,
        inputValue,
        setInputValue,
        chatState,
        uploadFiles,
        updateMessangerState,
        processRpcError,
    })
    const {activateChat, clearChat} = useChat({
        updateMessangerState,
        setMessages,
        clearFiles,
        getSettings,
        processRpcError,
    })

    const activeChat = settings.chats && settings.chats.find((chat) => chat.is_active)

    return (
        <Card className="chat-card border-0 h-100 d-flex flex-column">
            <Header settings={settings} activateChat={activateChat} clearChat={clearChat}
                    insertText={setInputValue}/>

            <Card.Body className="chat-body" ref={chatBodyRef}>
                <div className="chat-body-shadow"></div>
                {messages.map((message, index) => (
                    <Message
                        key={index}
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
                isLoading={isWaitingAnswer || chatState.status === 'loading'}
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
                {notifications.map((notification, index) => (
                    <Fragment key={index}>
                        <Notification notification={notification} onHide={() => removeNotification(notification.id)}/>
                    </Fragment>
                ))}
            </ToastContainer>
        </Card>
    )
}

export default Messenger
