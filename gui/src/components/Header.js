import React from 'react'
import {Button, Card, Dropdown, OverlayTrigger, Tooltip} from 'react-bootstrap'

function Header({settings, clearChat, insertText}) {
    return (
        <Card.Header className="chat-header rounded-0">
            <div className="logo user-select-none fw-semibold text-center">
                <i className="fa-solid fa-robot me-2" aria-hidden="true"></i>Copilot
            </div>

            <div className="actions d-flex align-items-center justify-content-end gap-2">
                <OverlayTrigger placement="bottom" overlay={<Tooltip id="tt-clear">Clear conversation</Tooltip>}>
                    <Button variant="outline-primary" onClick={clearChat} aria-label="Clear conversation">
                        <i className="fa-solid fa-eraser" aria-hidden="true"></i>
                    </Button>
                </OverlayTrigger>

                <Dropdown align="end">
                    <Dropdown.Toggle variant="outline-primary" aria-label="Insert prompt">
                        <i className="fa-solid fa-folder-closed" aria-hidden="true"></i>
                    </Dropdown.Toggle>

                    <Dropdown.Menu>
                        {settings.prompts?.map((prompt) => (
                            <Dropdown.Item key={prompt.name} onClick={() => insertText(prompt.text)}>
                                {prompt.name}
                            </Dropdown.Item>
                        ))}
                    </Dropdown.Menu>
                </Dropdown>
            </div>
        </Card.Header>
    )
}

export default React.memo(Header)
