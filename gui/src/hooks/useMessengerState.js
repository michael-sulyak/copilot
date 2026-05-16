import {useCallback, useMemo, useState} from 'react'
import {getTimestampNs} from '../utils'

const DEFAULT_CHAT_STATE = {
    status: 'idle',
    text: null,
    prevText: null,
    timestamp: 0,
}

function useMessengerState({activeChatUuid}) {
    const [chatStatesByUuid, setChatStatesByUuid] = useState({})

    const chatState = useMemo(
        () => (activeChatUuid ? (chatStatesByUuid[activeChatUuid] ?? DEFAULT_CHAT_STATE) : DEFAULT_CHAT_STATE),
        [activeChatUuid, chatStatesByUuid]
    )

    const updateMessengerState = useCallback(
        async ({text, status, timestamp, chatUuid} = {}) => {
            const targetChatUuid = chatUuid ?? activeChatUuid

            if (!targetChatUuid) {
                return
            }

            setChatStatesByUuid((prevChatStatesByUuid) => {
                const prev = prevChatStatesByUuid[targetChatUuid] ?? DEFAULT_CHAT_STATE
                const newTimestamp = timestamp === undefined ? getTimestampNs() : timestamp
                const newText = text === undefined ? prev.text : text
                const newStatus = status === undefined ? prev.status : status

                if (prev.timestamp <= newTimestamp) {
                    console.log('Chat state:', {
                        chatUuid: targetChatUuid,
                        timestamp: newTimestamp,
                        text: newText,
                        prevText: prev.text,
                        status: newStatus,
                    })

                    return {
                        ...prevChatStatesByUuid,
                        [targetChatUuid]: {
                            timestamp: newTimestamp,
                            text: newText,
                            prevText: prev.text,
                            status: newStatus,
                        },
                    }
                }

                return prevChatStatesByUuid
            })
        },
        [activeChatUuid]
    )

    return {
        chatState,
        updateMessengerState,
    }
}

export default useMessengerState
