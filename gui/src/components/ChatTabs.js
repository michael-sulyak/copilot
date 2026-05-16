import React, {useMemo} from 'react'
import {Button, Dropdown} from 'react-bootstrap'

function ChatTabs({settings, openChat, closeChat, activeChat, setActiveChat}) {
    const openedChats = settings.opened_chats ?? []
    const availableChats = settings.available_chats ?? []

    const handleCloseChat = async (event, chatUuid) => {
        event.preventDefault()
        event.stopPropagation()
        await closeChat(chatUuid)
    }

    return (
        <div className="chat-tabs">
            <div className="chat-tabs-scroll">
                {openedChats.map((chat) => (
                    <Button
                        active={(activeChat && activeChat.uuid) === chat.uuid}
                        key={chat.name}
                        type="button"
                        className={`chat-tab ${chat.is_active ? 'active' : ''}`}
                        onClick={() => (activeChat && activeChat.uuid) !== chat.uuid && setActiveChat(chat)}
                        title={chat.name}
                    >
                        <span className="chat-tab-title">{chat.name}</span>

                        {closeChat && (
                            <span
                                className="chat-tab-close"
                                role="button"
                                aria-label={`Close ${chat.name}`}
                                title={`Close ${chat.name}`}
                                onClick={(event) => handleCloseChat(event, chat.uuid)}
                            >
                                <i className="fa-solid fa-xmark" aria-hidden="true"></i>
                            </span>
                        )}
                    </Button>
                ))}

                <Dropdown className="chat-tabs-dropdown" align="end">
                    <Dropdown.Toggle className="chat-tab chat-tab-plus" aria-label="Open chat">
                        <i className="fa-solid fa-plus" aria-hidden="true"></i>
                    </Dropdown.Toggle>

                    <Dropdown.Menu>
                        {availableChats.length > 0 ? (
                            availableChats.map((chat) => (
                                <Dropdown.Item
                                    key={chat.name}
                                    onClick={() => openChat(chat.name)}
                                >
                                    {chat.name}
                                </Dropdown.Item>
                            ))
                        ) : (
                            <Dropdown.Item disabled>
                                No chats to open
                            </Dropdown.Item>
                        )}
                    </Dropdown.Menu>
                </Dropdown>
            </div>
        </div>
    )
}

export default React.memo(ChatTabs)