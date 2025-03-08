import React, {Fragment, useCallback, useEffect, useRef} from 'react'
import {Button, Card} from 'react-bootstrap'
import {CSSTransition} from 'react-transition-group'

const traverseFileTree = (item, path = '') =>
    new Promise((resolve, reject) => {
        if (item.isFile) {
            item.file(
                (file) => {
                    // Attach relativePath to preserve folder structure
                    file.relativePath = `${path}${file.name}`
                    resolve([file])
                },
                (error) => reject(error)
            )
        } else if (item.isDirectory) {
            const dirReader = item.createReader()
            let entries = []

            const readEntries = () => {
                dirReader.readEntries(
                    (results) => {
                        if (results.length === 0) {
                            // When done, traverse each entry in the folder recursively.
                            Promise.all(entries.map((entry) => traverseFileTree(entry, `${path}${item.name}/`)))
                                .then((filesArrays) => resolve(filesArrays.flat()))
                                .catch((error) => reject(error))
                        } else {
                            entries = entries.concat(results)
                            readEntries()
                        }
                    },
                    (error) => reject(error)
                )
            }
            readEntries()
        } else {
            resolve([]) // In case it's neither a file nor directory.
        }
    })

const processFileItems = (items) => {
    const filePromises = []

    for (let i = 0; i < items.length; i++) {
        const item = items[i]
        if (typeof item.webkitGetAsEntry === 'function') {
            const entry = item.webkitGetAsEntry()
            if (entry) {
                // Use traverseFileTree to handle both files and folders
                filePromises.push(traverseFileTree(entry))
            }
        } else if (item.kind === 'file') {
            const file = item.getAsFile()
            if (file) {
                filePromises.push(Promise.resolve([file]))
            }
        }
    }
    return Promise.all(filePromises).then((results) => results.flat())
}

// Unified handler for processing file data from the event.
const handleFilesFromEvent = ({event, dataSource, onFileUpload}) => {
    if (dataSource && dataSource.items) {
        processFileItems(dataSource.items)
            .then((files) => {
                if (files.length > 0) {
                    onFileUpload({target: {files}})
                }
            })
            .catch((error) => console.error('Error processing items:', error))
    } else if (dataSource && dataSource.files && dataSource.files.length > 0) {
        // Fallback for older browsers
        onFileUpload({target: {files: dataSource.files}})
    }
}

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
            if (event.clipboardData) {
                const items = Array.from(event.clipboardData.items)
                const hasFile = items.some((item) => item.kind === 'file')

                if (hasFile) {
                    handleFilesFromEvent({event, dataSource: event.clipboardData, onFileUpload})
                    event.preventDefault()
                }
            }
        },
        [onFileUpload]
    )
    const handleDragOver = useCallback((event) => {
        event.preventDefault()
    }, [])
    const handleDrop = useCallback(
        (event) => {
            event.preventDefault()
            if (event.dataTransfer) {
                handleFilesFromEvent({event, dataSource: event.dataTransfer, onFileUpload})
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
        <Card.Footer className="chat-footer flex-shrink-1" onDrop={handleDrop} onDragOver={handleDragOver}>
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
                            {file.preview ? <img src={file.preview} alt={`Preview ${index}`} /> : <Fragment />}
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
