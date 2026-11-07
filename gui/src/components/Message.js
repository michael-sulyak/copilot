import React, {Fragment, useEffect, useRef, useState} from 'react'
import Markdown from './Markdown'
import {Button, OverlayTrigger, Tooltip} from 'react-bootstrap'
import {API_BASE_URL, apiUrl} from '../api'
import {isImage} from '../utils'

function MessageAttachment({file}) {
    let url = null
    if (file.url) {
        try {
            const resolved = new URL(apiUrl(file.url))
            if (resolved.origin === API_BASE_URL.origin && ['http:', 'https:'].includes(resolved.protocol)) {
                url = resolved.href
            }
        } catch {
            // Keep the filename visible even if an attachment URL is unavailable.
        }
    }

    const content = (
        <>
            {url && isImage(file.name) && <img src={url} alt={file.name} loading="lazy" />}
            <span className="file-attachment-body">{file.name}</span>
        </>
    )

    return (
        <div className="file-attachment">
            {url ? (
                <a href={url} target="_blank" rel="noopener noreferrer">
                    {content}
                </a>
            ) : (
                content
            )}
        </div>
    )
}

function Message({message, addNotification: _addNotification, callButtonCallback, deleteMessage}) {
    const [copied, setCopied] = useState(false)
    const copyTimerRef = useRef(null)
    const attachments = message.attachments ?? message.__ui__?.attachments ?? []

    useEffect(() => {
        return () => {
            if (copyTimerRef.current) {
                clearTimeout(copyTimerRef.current)
            }
        }
    }, [])

    const copyText = async () => {
        try {
            await navigator.clipboard.writeText(message.body.content)

            setCopied(true)

            if (copyTimerRef.current) {
                clearTimeout(copyTimerRef.current)
            }

            copyTimerRef.current = setTimeout(() => setCopied(false), 1500)
        } catch (err) {
            console.error('Failed to copy text:', err)
        }
    }

    // const deleteCurrentMessage = async () => {
    //     await deleteMessage(message.uuid)
    // }

    const controllers = (
        <div className="message-controllers">
            <OverlayTrigger
                placement={message.from === 'user' ? 'left' : 'right'}
                overlay={<Tooltip>{copied ? 'Copied' : 'Copy'}</Tooltip>}
            >
                <Button type="button" onClick={copyText}>
                    <i className={`fa-solid ${copied ? 'fa-check' : 'fa-copy'}`} />
                </Button>
            </OverlayTrigger>
            {/*<Button type="button" onClick={deleteCurrentMessage}>*/}
            {/*    <i className="fa-solid fa-pen"></i>*/}
            {/*</Button>*/}
            {/*<Button type="button" onClick={deleteCurrentMessage}>*/}
            {/*    <i className="fa-solid fa-xmark"></i>*/}
            {/*</Button>*/}
        </div>
    )

    let buttons

    if (message.buttons) {
        buttons = (
            <div className="message-buttons">
                {message.buttons.map((button, index) => (
                    <div key={index}>
                        <div className="message-button" onClick={() => callButtonCallback(button.callback)}>
                            {button.name}
                        </div>
                    </div>
                ))}
            </div>
        )
    } else {
        buttons = <Fragment />
    }

    return (
        <div className={`message d-flex ${message.from === 'user' ? 'user-message' : 'received-message'}`}>
            {message.from === 'user' ? controllers : <Fragment />}
            <div style={{minWidth: 0}}>
                {message.body.content && (
                    <div className="message-text">
                        <Markdown content={message.body.content} />
                    </div>
                )}
                {attachments.length > 0 && (
                    <div className="file-attachments">
                        {attachments.map((file, index) => (
                            <MessageAttachment key={`${file.id ?? 'attachment'}-${index}`} file={file} />
                        ))}
                    </div>
                )}

                {buttons}

                <div className="message-footer">
                    {[message.body.duration, message.body.cost, message.body.total_tokens].every((x) => x === null || x === undefined) || (
                        <div className="message-footer-text">
                            <span>{Math.round(message.body.duration)} sec.</span>
                            <span className="mx-2">•</span>
                            <span>{Math.round(message.body.cost * 1_000_000) / 1_000_000}$</span>
                            <span className="mx-2">•</span>
                            <span>{Math.round(message.body.total_tokens)} tokens</span>
                        </div>
                    )}
                </div>
            </div>
            {message.from !== 'user' ? controllers : <Fragment />}
        </div>
    )
}

export default React.memo(Message)
