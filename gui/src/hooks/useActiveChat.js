import {useCallback, useEffect, useState} from 'react'

function useActiveChat({settings}) {
    const [activeChat, setActiveChat] = useState(null)

    useEffect(() => {
        if (!activeChat && settings.opened_chats && settings.opened_chats[0]) {
            setActiveChat(settings.opened_chats[0])
            console.log('Active chat:', activeChat)
        }
    }, [settings])

    return {activeChat, setActiveChat}
}

export default useActiveChat
