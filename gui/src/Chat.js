import React, {Fragment, useCallback, useEffect, useRef, useState} from 'react'
import {Card, ToastContainer} from 'react-bootstrap'
import Header from './components/Header'
import Message from './components/Message'
import Footer from './components/Footer'
import Notification from './components/Notification'
import useNotifications from './hooks/useNotifications'
import useSettings from './hooks/useSettings'
import useChatState from './hooks/useChatState'
import useFileUpload from './hooks/useFileUpload'
import useAudioRecording from './hooks/useAudioRecording'
import useDialog from './hooks/useDialog'
import useInput from './hooks/useInput'

function Chat() {
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
        [addNotification]
    )
    const {settings, getSettings} = useSettings({addNotification, processRpcError})
    const {chatState, updateChatState} = useChatState()
    const {attachedFiles, onFileUpload, removeAttachedFile, clearFiles, uploadFiles} = useFileUpload({
        addNotification,
        updateChatState,
    })
    const {inputValue, setInputValue, sendMessage, deleteMessage, callButtonCallback, isWaitingAnswer, handleInputChange} = useInput({
        textareaRef,
        addNotification,
        attachedFiles,
        clearFiles,
        chatState,
        updateChatState,
        chatBodyRef,
        setMessages,
    })
    const {recordingState, startRecording, stopRecording} = useAudioRecording({
        addNotification,
        inputValue,
        setInputValue,
        chatState,
        uploadFiles,
        updateChatState,
        processRpcError,
    })
    const {activateDialog, clearDialog} = useDialog({
        updateChatState,
        setMessages,
        clearFiles,
        getSettings,
        processRpcError,
    })

    const activeDialog = settings.dialogs && settings.dialogs.find((dialog) => dialog.is_active)

    return (
        <Card className="chat-card border-0 h-100 d-flex flex-column">
            <Header settings={settings} activateDialog={activateDialog} clearDialog={clearDialog} insertText={setInputValue} />

            <div className="chat-scroll-clip">
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
            </div>

            <Footer
                handleInputChange={handleInputChange}
                inputValue={inputValue}
                textareaRef={textareaRef}
                isLoading={isWaitingAnswer || chatState.status === 'loading'}
                activeDialog={activeDialog}
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
                        <Notification notification={notification} onHide={() => removeNotification(notification.id)} />
                    </Fragment>
                ))}
            </ToastContainer>
        </Card>
    )
}

export default Chat
