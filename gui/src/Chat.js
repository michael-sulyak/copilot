import React, {Fragment, useCallback, useEffect, useRef, useState} from 'react'
import {Card, ToastContainer} from 'react-bootstrap'
import Notification from './components/Notification'
import {v4 as uuidv4} from 'uuid'
import Header from './components/Header'
import Message from './components/Message'
import Footer from './components/Footer'
import {getTimestampNs, isImage} from './utils'


function Chat() {
    const MAX_FILE_SIZE = 10 * 1024 * 1024 // 10 MB

    const chatBodyRef = useRef(null)
    const [inputValue, setInputValue] = useState('')
    const [notifications, setNotifications] = useState([])
    const [settings, setSettings] = useState({})
    const [messages, setMessages] = useState([])
    const [isWaitingAnswer, setIsWaitingAnswer] = useState(false)
    const mediaRecorderRef = useRef(null)
    const [recordingState, setRecordingState] = useState({
        status: 'off',
    })
    const [chatState, setChatState] = useState({
        status: 'idle',
        text: null,
        prevText: null,
        timestamp: 0,
    })
    const textareaRef = useRef(null)
    const rpcClient = window.rpcClient
    const activeDialog = settings.dialogs && settings.dialogs.filter(dialog => dialog.is_active)[0]
    const fileInputRef = useRef(null)
    const [attachedFiles, setAttachedFiles] = useState([])
    const [userInteractionTrigger, setUserInteractionTrigger] = useState(null)
    const [needToScrollChat, setNeedToScrollChat] = useState(null)

    const resetTextareaHeight = () => {
        textareaRef.current.style.height = 'auto'
    }

    const addNotification = useCallback((message) => {
        setNotifications((notifications) => [...notifications, {'id': uuidv4(), 'content': message}])
    }, [setNotifications])

    useEffect(() => {
        rpcClient.on('show_notification', (message) => {
            addNotification(message)
        })

        return () => {
            rpcClient.off('show_notification')
        }
    }, [addNotification, rpcClient])

    const updateChatState = useCallback(async ({text = undefined, status = undefined, timestamp = undefined}) => {
        setChatState(chatState => {
            if (timestamp === undefined) {
                timestamp = getTimestampNs()
            }

            let prevText

            if (text === undefined) {
                text = chatState.text
                prevText = chatState.prevText
            } else {
                prevText = chatState.text
            }

            if (status === undefined) {
                status = chatState.status
            }

            if (chatState.timestamp <= timestamp) {
                console.log({
                    timestamp,
                    text,
                    prevText,
                    status,
                })
                return {
                    timestamp,
                    text,
                    prevText,
                    status,
                }
            }

            return chatState
        })

    }, [setChatState])

    useEffect(() => {
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
    }, [updateChatState, userInteractionTrigger, chatState, setMessages, rpcClient, setUserInteractionTrigger])

    const getSettings = useCallback(async () => {
        const settings = await rpcClient.call('get_settings', [])
        setSettings(settings)
        console.log('Settings:')
        console.log(settings)
    }, [rpcClient])

    useEffect(() => {
        getSettings()
    }, [getSettings])

    const getHistory = useCallback(async () => {
        const history = await rpcClient.call('get_history', [])
        console.log('History:')
        console.log(history)
        setMessages(history)
    }, [rpcClient])

    const clearFiles = useCallback(async () => {
        attachedFiles.map(file => URL.revokeObjectURL(file.preview))
        await setAttachedFiles([])
    }, [attachedFiles])

    useEffect(() => {
        getHistory()
    }, [getHistory])

    const activateDialog = useCallback(async (dialogName) => {
        await updateChatState({status: 'loading', text: null})
        await setMessages([])
        await clearFiles()
        await rpcClient.call('activate_dialog', [dialogName])
        await getSettings()
        await updateChatState({status: 'idle', text: null})
    }, [updateChatState, setMessages, rpcClient, getSettings, clearFiles])

    const clearDialog = useCallback(async () => {
        await setMessages([])
        await clearFiles()
        await rpcClient.call('clear_dialog', [])
    }, [rpcClient, setMessages, clearFiles])

    const updateTextareaHeight = useCallback(() => {
        resetTextareaHeight()
        const maxHeight = Math.max(200, window.screen.height * 0.1)
        let newHeight = textareaRef.current.scrollHeight + 2

        if (newHeight > maxHeight) {
            newHeight = maxHeight
        }

        textareaRef.current.style.height = `${newHeight}px`
        chatBodyRef.current.style.paddingBottom = `calc(${newHeight}px + 3rem)`
    }, [])

    const handleInputChange = useCallback((event) => {
        setInputValue(event.target.value)
    }, [setInputValue])

    const removeNotification = useCallback((notificationId) => {
        setNotifications((notifications) => (notifications.filter((notification) => notification.id !== notificationId)))
    }, [setNotifications])

    const showMsgAboutVPN = useCallback(async () => {
        await addNotification('You need to turn on VPN')
    }, [addNotification])

    useEffect(() => {
        updateTextareaHeight()
    }, [inputValue, updateTextareaHeight])

    const needToTurnOnVPN = async () => {
        const location = await fetch(
            'https://www.cloudflare.com/cdn-cgi/trace',
        ).then(
            response => response.text(),
        ).then(
            data => data.match(/loc=(.*)/)[1],
        ).catch(
            err => addNotification(String(err)),
        )

        return location === 'RU'
    }

    const sendMessage = useCallback(async () => {
        console.log('sendMessage')
        const message = inputValue.trim()

        if (!message) {
            return
        }

        await setIsWaitingAnswer(true)
        await setInputValue('')
        textareaRef.current.focus()

        if (await needToTurnOnVPN()) {
            await showMsgAboutVPN()
            await setInputValue(message)
            await setIsWaitingAnswer(false)
            return
        }

        const preparedMessage = {
            from: 'user',
            body: {
                content: message,
                attachments: attachedFiles.map(attachedFile => attachedFile.id),
            },
            __ui__: {
                attachments: attachedFiles,
            },
        }

        await setMessages((messages) => [...messages, preparedMessage])

        await setUserInteractionTrigger(true)
        await setNeedToScrollChat(true)

        await rpcClient.call('process_message', [preparedMessage])

        await clearFiles()
        await setIsWaitingAnswer(false)
    }, [rpcClient, inputValue, attachedFiles, showMsgAboutVPN, clearFiles, setUserInteractionTrigger, setNeedToScrollChat])

    const callButtonCallback = useCallback(async (buttonCallback) => {
        setIsWaitingAnswer(true)

        if (await needToTurnOnVPN()) {
            await showMsgAboutVPN()
            await setIsWaitingAnswer(false)
            return
        }

        const preparedMessage = {
            from: 'user', body: {callback: buttonCallback},
        }

        await setUserInteractionTrigger(true)
        const response = await rpcClient.call('process_message', [preparedMessage])

        console.log('Response:')
        console.log(response)

        if (response !== null) {
            setMessages((messages) => [...messages, response])
        }

        setIsWaitingAnswer(false)
    }, [rpcClient, showMsgAboutVPN])

    const handleKeyPress = useCallback(async (event) => {
        if (!(event.keyCode === 13 && (event.metaKey || event.ctrlKey))) {
            return
        }

        await sendMessage()
    }, [sendMessage])

    useEffect(() => {
        document.addEventListener('keydown', handleKeyPress)

        return () => {
            document.removeEventListener('keydown', handleKeyPress)
        }
    }, [handleKeyPress])

    useEffect(() => {
        textareaRef.current.focus()
    }, [])

    const executeScroll = () => chatBodyRef.current?.lastElementChild?.scrollIntoView({
        behavior: 'smooth', block: 'start',
    })

    useEffect(() => {
        if (needToScrollChat) {
            executeScroll()
            setNeedToScrollChat(false)
        }
    }, [needToScrollChat])

    const uploadFiles = useCallback(async ({files, updateChatStateText = true, callback}) => {
        const formData = new FormData()

        files.forEach((file, index) => {
            formData.append('files', file) // Append each file to the form data
        })

        const xhr = new XMLHttpRequest()
        xhr.open('POST', 'http://localhost:8123/upload-file', true) // Adjust the URL to match your backend endpoint

        if (updateChatStateText) {
            xhr.upload.onprogress = async (event) => {
                if (event.lengthComputable) {
                    const percentComplete = Math.round((event.loaded / event.total) * 100)
                    await updateChatState({text: `File uploading... (${percentComplete}%)`})
                }
            }
        }

        xhr.onload = async () => {
            const timestamp = getTimestampNs()

            if (updateChatStateText) {
                if (xhr.status === 200) {
                    await updateChatState({text: 'Files uploaded successfully', timestamp})
                } else {
                    await updateChatState({text: 'Failed to upload files', timestamp})
                }

                setTimeout(() => {
                    updateChatState({text: null, timestamp: timestamp + 1})
                }, 2000)
            } else if (xhr.status !== 200) {
                await addNotification('Failed to upload files')
            }
        }

        xhr.onreadystatechange = () => {
            if (xhr.readyState === 4) {
                callback(xhr.response)
            }
        }

        xhr.send(formData)
    }, [updateChatState])


    const startRecording = useCallback(async () => {
        if (recordingState.status !== 'off') {
            return
        }

        let stream

        try {
            stream = await navigator.mediaDevices.getUserMedia({audio: true})
        } catch (err) {
            addNotification('Error accessing microphone: ' + err.message)
            return
        }

        setRecordingState({status: 'on', startedAt: new Date()})
        await updateChatState({text: 'Recording...', timestamp: getTimestampNs()})
        let chunks = []

        const mediaRecorder = new MediaRecorder(stream)
        mediaRecorderRef.current = mediaRecorder

        mediaRecorder.ondataavailable = (event) => {
            if (event.data && event.data.size > 0) {
                chunks.push(event.data)
            }
        }

        mediaRecorder.onstop = async () => {
            setRecordingState({status: 'processing'})
            await updateChatState({text: 'Uploading audio...', timestamp: getTimestampNs()})
            const blob = new Blob(chunks, {type: 'audio/webm'})
            stream.getTracks().forEach(track => track.stop())

            const fileName = `recording_${Date.now()}.webm`
            const audioFile = new File([blob], fileName, {type: blob.type})

            await uploadFiles({
                files: [audioFile],
                updateChatStateText: false,
                callback: async (response) => {
                    const parsedResponse = JSON.parse(response)
                    const uploadedFiles = parsedResponse.files

                    await updateChatState({text: 'Processing audio...', timestamp: getTimestampNs()})
                    const result = await rpcClient.call('process_audio', [uploadedFiles[0].id])

                    setRecordingState({status: 'off'})
                    await updateChatState({text: null, timestamp: getTimestampNs()})

                    if (result.error) {
                        await addNotification(result.error)
                    } else {
                        await setInputValue(inputValue ? `${inputValue}\n\n${result.text}` : result.text)
                    }
                },
            })
        }

        mediaRecorder.start()
    }, [inputValue, addNotification, updateChatState, recordingState, rpcClient, uploadFiles])

    const stopRecording = useCallback(async () => {
        if (mediaRecorderRef.current && recordingState.status === 'on') {
            mediaRecorderRef.current.stop()
        } else {
            addNotification('Not currently recording.')
        }
    }, [addNotification, recordingState])


    const onFileUpload = async (e) => {
        if (!e.target.files) {
            return
        }

        const files = Array.from(e.target.files)
        const validFiles = files.filter(file => file.size <= MAX_FILE_SIZE)

        console.log(files)

        if (validFiles.length !== files.length) {
            await addNotification(
                `Some files were not uploaded due to size.\n`
                + `Max size: ${MAX_FILE_SIZE / 1024 / 1024}.`,
            )

            return
        }

        await uploadFiles({
            files: validFiles, callback: async (response) => {
                const uploadedFiles = JSON.parse(response).files
                console.log({uploadedFiles})

                const imageUrls = files.map(file => URL.createObjectURL(file))

                const newFiles = files.map((file, index) => ({
                    ...uploadedFiles[index],
                    preview: isImage(file.name) ? imageUrls[index] : null,
                    type: file.type,
                }))

                await setAttachedFiles(prevFiles => [...prevFiles, ...newFiles])
                await addNotification(`Uploaded ${validFiles.map(file => file.name).join(', ')}`)
            },
        })
    }

    const removeAttachedFile = (fileId) => {
        setAttachedFiles(attachedFiles => attachedFiles.filter(file => {
            if (file.id === fileId) {
                URL.revokeObjectURL(file.preview)
                return false
            } else {
                return true
            }
        }))
    }

    return (<Card className="chat-card border-0 h-100 d-flex flex-column">
        <Header
            settings={settings}
            activateDialog={activateDialog}
            clearDialog={clearDialog}
            insertText={setInputValue}
        />
        <Card.Body className="chat-body" ref={chatBodyRef}>
            <div className="chat-body-shadow"></div>
            {messages.map((message, index) => (
                <Message
                    key={index}
                    message={message}
                    addNotification={addNotification}
                    callButtonCallback={callButtonCallback}
                />
            ))}
        </Card.Body>
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
        <ToastContainer
            position="top-center"
            className={'position-fixed'}
        >
            {notifications.map((notification, index) => (<Fragment key={index}>
                <Notification
                    notification={notification}
                    onHide={() => removeNotification(notification.id)}
                />
            </Fragment>))}
        </ToastContainer>
    </Card>)
}

export default Chat