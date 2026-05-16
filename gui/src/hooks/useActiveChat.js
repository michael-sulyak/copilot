import {useEffect, useState} from 'react'

function useActiveChat({settings}) {
    const [activeChat, setActiveChat] = useState(null)

    useEffect(() => {
        const openedChats = settings.opened_chats ?? []

        setActiveChat((currentActiveChat) => {
            if (openedChats.length === 0) {
                return null
            }

            if (!currentActiveChat) {
                return openedChats[0]
            }

            return openedChats.find((chat) => chat.uuid === currentActiveChat.uuid) ?? openedChats[0]
        })
    }, [settings.opened_chats])

    return {activeChat, setActiveChat}
}

export default useActiveChat
