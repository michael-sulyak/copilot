import React from 'react'
import {Button, Card, Dropdown, OverlayTrigger, Tooltip} from 'react-bootstrap'

function Header({settings, clearChat, insertText}) {
    return (
        <Card.Header className="chat-header rounded-0">
            <div className="logo user-select-none fw-semibold text-center">
                <i className="fa-solid fa-robot me-2" aria-hidden="true"></i>Copilot
            </div>

            <div className="actions d-flex align-items-center justify-content-end gap-2">
                <OverlayTrigger placement="bottom" overlay={<Tooltip>Clear conversation</Tooltip>}>
                    <Button variant="outline-primary" onClick={clearChat} aria-label="Clear conversation">
                        <i className="fa-solid fa-eraser" aria-hidden="true"></i>
                    </Button>
                </OverlayTrigger>

                <Dropdown className="chat-dropdown" align="end">
                    <OverlayTrigger placement="bottom" overlay={<Tooltip>Insert prompt</Tooltip>}>
                        <Dropdown.Toggle variant="outline-primary" aria-label="Insert prompt">
                            <i className="fa-solid fa-folder-closed" aria-hidden="true"></i>
                        </Dropdown.Toggle>
                    </OverlayTrigger>

                    <Dropdown.Menu>
                        <Dropdown.Header>Insert a saved prompt</Dropdown.Header>
                        {settings.prompts?.length ? (
                            settings.prompts.map((prompt) => (
                                <Dropdown.Item as="button" key={prompt.name} onClick={() => insertText(prompt.text)}>
                                    <span className="chat-menu-label">{prompt.name}</span>
                                </Dropdown.Item>
                            ))
                        ) : (
                            <Dropdown.Item disabled>No saved prompts</Dropdown.Item>
                        )}
                    </Dropdown.Menu>
                </Dropdown>
            </div>
        </Card.Header>
    )
}

export default React.memo(Header)
