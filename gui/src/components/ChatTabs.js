import React, {useCallback, useLayoutEffect, useRef, useState} from 'react'
import {Button, Dropdown, OverlayTrigger, Tooltip} from 'react-bootstrap'

const EMPTY_CHATS = []
const EMPTY_COUNTS = {}

function MessageCount({count, id}) {
    const label = count === undefined ? 'Open chat to load message history' : `${count} ${count === 1 ? 'message' : 'messages'}`
    return (
        <OverlayTrigger placement="bottom" overlay={<Tooltip>{label}</Tooltip>}>
            <span className="chat-tab-message-count" aria-label={label}>
                <span id={id} className="visually-hidden">
                    {label}
                </span>
                <span aria-hidden="true">{count ?? '–'}</span>
            </span>
        </OverlayTrigger>
    )
}

function ChatTabs({settings, messageCounts = EMPTY_COUNTS, openChat, closeChat, activeChat, setActiveChat}) {
    const openedChats = settings.opened_chats ?? EMPTY_CHATS
    const availableChats = settings.available_chats ?? EMPTY_CHATS
    const scrollRef = useRef(null)
    const tabRefs = useRef(new Map())
    const closingRef = useRef(new Set())
    const focusAfterCloseRef = useRef(null)
    const chatListRef = useRef(null)
    const [closingChats, setClosingChats] = useState(new Set())
    const [scrollState, setScrollState] = useState({left: false, right: false})
    const hasOverflow = scrollState.left || scrollState.right
    const activeUuid = activeChat?.uuid
    const focusableUuid = openedChats.some((chat) => chat.uuid === activeUuid) ? activeUuid : openedChats[0]?.uuid

    const updateScrollState = useCallback(() => {
        const strip = scrollRef.current
        if (!strip) return
        const left = strip.scrollLeft > 1
        const right = strip.scrollLeft + strip.clientWidth < strip.scrollWidth - 1
        setScrollState((previous) => (previous.left === left && previous.right === right ? previous : {left, right}))
    }, [])

    const revealTab = useCallback((chatUuid) => {
        const strip = scrollRef.current
        const tab = tabRefs.current.get(chatUuid)?.parentElement
        if (!strip || !tab) return
        const stripBounds = strip.getBoundingClientRect()
        const tabBounds = tab.getBoundingClientRect()
        // Only move this strip, never the conversation or the page.
        if (tabBounds.width > stripBounds.width || tabBounds.left < stripBounds.left) strip.scrollLeft += tabBounds.left - stripBounds.left
        else if (tabBounds.right > stripBounds.right) strip.scrollLeft += tabBounds.right - stripBounds.right
    }, [])

    useLayoutEffect(() => {
        const strip = scrollRef.current
        const updateLayout = () => {
            revealTab(activeUuid)
            updateScrollState()
        }
        updateLayout()
        window.addEventListener('resize', updateLayout)
        const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(updateLayout)
        if (strip) {
            observer?.observe(strip)
            // Font/title changes can resize the tabs without resizing the strip.
            Array.from(strip.children).forEach((tab) => observer?.observe(tab))
        }
        return () => {
            window.removeEventListener('resize', updateLayout)
            observer?.disconnect()
        }
    }, [activeUuid, openedChats, hasOverflow, revealTab, updateScrollState])

    useLayoutEffect(() => {
        const pending = focusAfterCloseRef.current
        if (!pending || openedChats.some((chat) => chat.uuid === pending.uuid)) return
        focusAfterCloseRef.current = null
        // Wait for React to remove the tab, rather than guessing when the RPC's
        // state updates will commit. Leave focus alone if the user moved it.
        if (document.activeElement !== document.body && document.activeElement !== pending.button) return
        const targetUuid = tabRefs.current.has(pending.nextUuid) ? pending.nextUuid : focusableUuid
        const target = tabRefs.current.get(targetUuid) ?? chatListRef.current
        target?.focus({preventScroll: true})
        revealTab(targetUuid)
    }, [openedChats, focusableUuid, revealTab])

    const scrollTabs = (direction) => {
        const strip = scrollRef.current
        const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
        if (strip)
            strip.scrollBy({
                left: direction * strip.clientWidth * 0.8,
                behavior: reduceMotion ? 'auto' : 'smooth',
            })
    }

    const handleTabKeyDown = (event, index) => {
        let nextIndex
        if (event.key === 'ArrowRight') nextIndex = (index + 1) % openedChats.length
        else if (event.key === 'ArrowLeft') nextIndex = (index - 1 + openedChats.length) % openedChats.length
        else if (event.key === 'Home') nextIndex = 0
        else if (event.key === 'End') nextIndex = openedChats.length - 1
        else return
        event.preventDefault()
        const nextChat = openedChats[nextIndex]
        tabRefs.current.get(nextChat.uuid)?.focus({preventScroll: true})
        revealTab(nextChat.uuid)
        if (nextChat.uuid !== activeUuid) setActiveChat(nextChat)
    }

    const handleCloseChat = async (event, chatUuid) => {
        if (closingRef.current.has(chatUuid)) return
        const closeButton = event.currentTarget
        const index = openedChats.findIndex((chat) => chat.uuid === chatUuid)
        const nextChat = openedChats[index + 1] ?? openedChats[index - 1]
        if (document.activeElement === closeButton) {
            focusAfterCloseRef.current = {uuid: chatUuid, nextUuid: nextChat?.uuid, button: closeButton}
        }
        closingRef.current.add(chatUuid)
        setClosingChats(new Set(closingRef.current))
        try {
            const closed = await closeChat(chatUuid)
            if (closed === false && focusAfterCloseRef.current?.uuid === chatUuid) {
                focusAfterCloseRef.current = null
                if (document.activeElement === document.body) closeButton.focus({preventScroll: true})
            }
        } finally {
            closingRef.current.delete(chatUuid)
            setClosingChats(new Set(closingRef.current))
        }
    }

    return (
        <nav className="chat-tabs" aria-label="Chat navigation">
            {hasOverflow && (
                <OverlayTrigger placement="bottom" overlay={<Tooltip>Scroll chats left</Tooltip>}>
                    <Button
                        type="button"
                        className="chat-tabs-control chat-tabs-nav"
                        aria-label="Scroll chats left"
                        disabled={!scrollState.left}
                        onClick={() => scrollTabs(-1)}
                    >
                        <i className="fa-solid fa-chevron-left" aria-hidden="true"></i>
                    </Button>
                </OverlayTrigger>
            )}
            <div
                className={`chat-tabs-viewport${scrollState.left ? ' can-scroll-left' : ''}${scrollState.right ? ' can-scroll-right' : ''}`}
            >
                <div className="chat-tabs-scroll" ref={scrollRef} onScroll={updateScrollState} role="group" aria-label="Open chats">
                    {openedChats.map((chat, index) => {
                        const isActive = activeUuid === chat.uuid
                        const isClosing = closingChats.has(chat.uuid)
                        return (
                            <div className={`chat-tab${isActive ? ' active' : ''}`} key={chat.uuid} aria-busy={isClosing || undefined}>
                                <button
                                    ref={(node) => {
                                        if (node) tabRefs.current.set(chat.uuid, node)
                                        else tabRefs.current.delete(chat.uuid)
                                    }}
                                    type="button"
                                    className="chat-tab-select"
                                    aria-label={chat.name}
                                    aria-describedby={`chat-message-count-${chat.uuid}`}
                                    aria-current={isActive ? 'page' : undefined}
                                    tabIndex={focusableUuid === chat.uuid ? 0 : -1}
                                    onClick={() => !isActive && setActiveChat(chat)}
                                    onKeyDown={(event) => handleTabKeyDown(event, index)}
                                    onFocus={() => revealTab(chat.uuid)}
                                >
                                    <span className="chat-tab-title">{chat.name}</span>
                                    <MessageCount count={messageCounts[chat.uuid]} id={`chat-message-count-${chat.uuid}`} />
                                </button>
                                {closeChat && (
                                    <button
                                        type="button"
                                        className="chat-tab-close"
                                        aria-label={`Close ${chat.name}`}
                                        disabled={isClosing}
                                        onClick={(event) => handleCloseChat(event, chat.uuid)}
                                    >
                                        <i className={`fa-solid ${isClosing ? 'fa-spinner fa-spin' : 'fa-xmark'}`} aria-hidden="true"></i>
                                    </button>
                                )}
                            </div>
                        )
                    })}
                </div>
            </div>
            {hasOverflow && (
                <OverlayTrigger placement="bottom" overlay={<Tooltip>Scroll chats right</Tooltip>}>
                    <Button
                        type="button"
                        className="chat-tabs-control chat-tabs-nav"
                        aria-label="Scroll chats right"
                        disabled={!scrollState.right}
                        onClick={() => scrollTabs(1)}
                    >
                        <i className="fa-solid fa-chevron-right" aria-hidden="true"></i>
                    </Button>
                </OverlayTrigger>
            )}
            <div className="chat-tabs-actions">
                <Dropdown className="chat-dropdown" align="end">
                    <OverlayTrigger placement="bottom" overlay={<Tooltip>All open chats</Tooltip>}>
                        <Dropdown.Toggle
                            ref={chatListRef}
                            className="chat-tabs-control chat-tabs-list"
                            aria-label={`All open chats (${openedChats.length})`}
                            disabled={openedChats.length === 0}
                        >
                            <i className="fa-solid fa-list" aria-hidden="true"></i>
                            <span className="chat-tabs-count" aria-hidden="true">
                                {openedChats.length}
                            </span>
                        </Dropdown.Toggle>
                    </OverlayTrigger>
                    <Dropdown.Menu>
                        <Dropdown.Header>Open conversations · {openedChats.length}</Dropdown.Header>
                        {openedChats.map((chat) => (
                            <Dropdown.Item
                                as="button"
                                key={chat.uuid}
                                active={activeUuid === chat.uuid}
                                aria-current={activeUuid === chat.uuid ? 'page' : undefined}
                                onClick={() => setActiveChat(chat)}
                            >
                                <span className="chat-menu-label">{chat.name}</span>
                                <MessageCount count={messageCounts[chat.uuid]} />
                            </Dropdown.Item>
                        ))}
                    </Dropdown.Menu>
                </Dropdown>
                <Dropdown className="chat-dropdown" align="end">
                    <Dropdown.Toggle
                        className="chat-tabs-control chat-tabs-new"
                        aria-label="Open new chat"
                        disabled={availableChats.length === 0}
                    >
                        <i className="fa-solid fa-plus" aria-hidden="true"></i>
                        <span className="chat-tabs-new-label">New chat</span>
                    </Dropdown.Toggle>
                    <Dropdown.Menu>
                        <Dropdown.Header>Start a new chat</Dropdown.Header>
                        {availableChats.length > 0 ? (
                            availableChats.map((chat) => (
                                <Dropdown.Item as="button" key={chat.name} onClick={() => openChat(chat.name)}>
                                    <span className="chat-menu-label">{chat.name}</span>
                                </Dropdown.Item>
                            ))
                        ) : (
                            <Dropdown.Item disabled>No chats available</Dropdown.Item>
                        )}
                    </Dropdown.Menu>
                </Dropdown>
            </div>
        </nav>
    )
}

export default React.memo(ChatTabs)
