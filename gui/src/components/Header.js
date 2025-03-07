import React from 'react'
import {Button, Card, Dropdown} from 'react-bootstrap'


function Header({settings, activateDialog, clearDialog, insertText}) {
    return (
        <Card.Header className="chat-header rounded-0 flex-shrink-1 d-flex align-items-center">
            <div className="logo user-select-none flex-grow-1">
                <span className="position-relative">
                    Copilot
                </span>
            </div>
            <div className="d-flex align-items-center">
                <Button
                    variant="outline-primary"
                    onClick={clearDialog}
                >
                    <i className="fa-solid fa-eraser"></i>
                </Button>
                <Dropdown className="ms-2" variant="dark">
                    <Dropdown.Toggle
                        variant="outline-primary"
                    >
                        <i className="fa-solid fa-folder-closed"></i>
                    </Dropdown.Toggle>
                    <Dropdown.Menu>
                        {settings.prompts?.map((prompt, index) => (
                            <Dropdown.Item
                                key={index}
                                onClick={() => insertText(prompt.text)}
                            >
                                {prompt.name}
                            </Dropdown.Item>
                        ))}
                    </Dropdown.Menu>
                </Dropdown>
                <Dropdown className="ms-2" variant="dark">
                    <Dropdown.Toggle
                        variant="outline-primary"
                    >
                        {
                            settings.dialogs
                                ? settings.dialogs.filter(dialog => dialog.is_active)[0].name
                                :
                                'Default'
                        }
                    </Dropdown.Toggle>
                    <Dropdown.Menu>
                        {settings.dialogs?.map((dialog, index) => (
                            <Dropdown.Item
                                key={index}
                                active={dialog.is_active}
                                onClick={() => !dialog.is_active && activateDialog(dialog.name)}
                            >
                                {dialog.name}
                            </Dropdown.Item>
                        ))}
                    </Dropdown.Menu>
                </Dropdown>
            </div>
        </Card.Header>
    )
}

export default React.memo(Header)
