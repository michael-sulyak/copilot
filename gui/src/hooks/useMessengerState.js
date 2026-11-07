import {useCallback, useMemo, useState} from 'react'
import {getUiTimestamp} from '../utils'

const DEFAULT_CHAT_STATE = {
    status: 'idle',
    text: null,
    prevText: null,
    timestamp: 0,
    revision: 0,
}

function useMessengerState({activeChatUuid}) {
    const [chatStatesByUuid, setChatStatesByUuid] = useState({})

    const chatState = useMemo(
        () => (activeChatUuid ? (chatStatesByUuid[activeChatUuid] ?? DEFAULT_CHAT_STATE) : DEFAULT_CHAT_STATE),
        [activeChatUuid, chatStatesByUuid]
    )

    const updateMessengerState = useCallback(
        async ({text, status, timestamp, revision, chatUuid} = {}) => {
            const targetChatUuid = chatUuid ?? activeChatUuid

            if (!targetChatUuid) {
                return
            }

            const newTimestamp = timestamp === undefined ? getUiTimestamp() : timestamp
            setChatStatesByUuid((prevChatStatesByUuid) => {
                const prev = prevChatStatesByUuid[targetChatUuid] ?? DEFAULT_CHAT_STATE
                if (revision !== undefined && revision < prev.revision) return prevChatStatesByUuid
                const newText = text === undefined ? prev.text : text
                const newStatus = status === undefined ? prev.status : status

                if (prev.timestamp <= newTimestamp) {
                    return {
                        ...prevChatStatesByUuid,
                        [targetChatUuid]: {
                            timestamp: newTimestamp,
                            revision: revision ?? prev.revision,
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
