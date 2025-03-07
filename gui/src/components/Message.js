import React, {Fragment} from 'react'
import Markdown from './Markdown'
import {Button} from 'react-bootstrap'

function Message({message, addNotification, callButtonCallback}) {
    const copyText = () => {
        navigator.clipboard.writeText(message.body.content)
        addNotification('Copied')
    }

    const controllers = (
        <div className="message-controllers">
            <Button type="button" onClick={copyText}>
                <i className="fa-solid fa-copy" />
            </Button>
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
                <div className="message-text">
                    <Markdown content={message.body.content} />
                </div>
                {message.__ui__ && message.__ui__.attachments && (
                    <div className="file-attachments">
                        {message.__ui__.attachments.map((file, index) => (
                            <div className="file-attachment" key={index}>
                                <div className="file-attachment-body">{file.name}</div>
                            </div>
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
