import React, {Fragment, useCallback, useEffect, useRef} from 'react'
import {Button, Card} from 'react-bootstrap'
import {CSSTransition} from 'react-transition-group'

function Footer({
    handleInputChange,
    inputValue,
    textareaRef,
    isLoading,
    activeDialog,
    onFileUpload,
    fileInputRef,
    attachedFiles,
    sendMessage,
    removeAttachedFile,
    chatState,
    recordingState,
    startRecording,
    stopRecording,
}) {
    const chatStatusContainerRef = useRef()
    const pasteHandlerRef = useRef()

    const handlePaste = useCallback(
        (event) => {
            const items = event.clipboardData.items

            let files = []

            for (let i = 0; i < items.length; i++) {
                if (items[i].kind === 'file') {
                    files.push(items[i].getAsFile())
                }
            }

            if (files.length > 0) {
                onFileUpload({target: {files}})
                event.preventDefault()
            }
        },
        [onFileUpload]
    )

    useEffect(() => {
        pasteHandlerRef.current = handlePaste
        document.addEventListener('paste', pasteHandlerRef.current)

        return () => {
            document.removeEventListener('paste', pasteHandlerRef.current)
        }
    }, [handlePaste])

    return (
        <Card.Footer className="chat-footer flex-shrink-1">
            <CSSTransition
                in={!!chatState.text}
                mountOnEnter
                unmountOnExit
                classNames="chat-status-transition"
                nodeRef={chatStatusContainerRef}
                timeout={2000}
            >
                <div className="chat-status-container" ref={chatStatusContainerRef}>
                    <div className="chat-status">
                        <div className="chat-status-content">
                            <i className="fa-solid fa-circle-info"></i> {chatState.text || chatState.prevText}
                        </div>
                    </div>
                </div>
            </CSSTransition>
            <div className="input-group">
                <textarea
                    className="form-control"
                    id="user-input"
                    rows="1"
                    placeholder="Type your message"
                    onChange={handleInputChange}
                    value={inputValue}
                    ref={textareaRef}
                    disabled={isLoading}
                />
                <Button
                    type="submit"
                    className={recordingState.status === 'off' ? 'input-btn' : 'input-btn active'}
                    onClick={recordingState.status === 'off' ? startRecording : stopRecording}
                    disabled={recordingState.status === 'processing'}
                >
                    <i className="fa-solid fa-microphone"></i>
                </Button>
                {activeDialog && activeDialog.files_are_supported ? (
                    <Fragment>
                        <input type="file" onChange={onFileUpload} multiple style={{display: 'none'}} ref={fileInputRef} />
                        <Button type="submit" className="input-btn" onClick={() => fileInputRef.current.click()}>
                            <i className="fa-solid fa-paperclip"></i>
                        </Button>
                    </Fragment>
                ) : (
                    <Fragment />
                )}
                <Button
                    type="submit"
                    className="btn"
                    id="send-btn"
                    onClick={sendMessage}
                    disabled={isLoading || recordingState.status !== 'off'}
                >
                    {isLoading || recordingState.status !== 'off' ? (
                        <span className="spinner-border spinner-border-sm" role="status" aria-hidden="true" />
                    ) : (
                        <i className="fa-solid fa-paper-plane"></i>
                    )}
                </Button>
            </div>
            {attachedFiles.length > 0 && !isLoading && (
                <div className="file-attachments">
                    {attachedFiles.map((file, index) => (
                        <div className="file-attachment" key={index}>
                            {file.preview ? <img key={index} src={file.preview} alt={`Preview ${index}`} /> : <Fragment />}

                            <div className="file-attachment-body">{file.name}</div>
                            <div className="file-attachment-close" onClick={() => removeAttachedFile(file.id)}>
                                <i className="fa-solid fa-xmark"></i>
                            </div>
                        </div>
                    ))}
                    <div className="image-previews"></div>
                </div>
            )}
        </Card.Footer>
    )
}

export default React.memo(Footer)
