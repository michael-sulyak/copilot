import {useCallback, useState} from 'react'
import {getTimestampNs} from '../utils'

function useChatState() {
    const [chatState, setChatState] = useState({
        status: 'idle',
        text: null,
        prevText: null,
        timestamp: 0,
    })

    const updateChatState = useCallback(async ({text, status, timestamp}) => {
        setChatState((prev) => {
            const newTimestamp = timestamp === undefined ? getTimestampNs() : timestamp
            const newText = text === undefined ? prev.text : text
            const newStatus = status === undefined ? prev.status : status

            if (prev.timestamp <= newTimestamp) {
                console.log({timestamp: newTimestamp, text: newText, prevText: prev.text, status: newStatus})
                return {timestamp: newTimestamp, text: newText, prevText: prev.text, status: newStatus}
            }

            return prev
        })
    }, [])

    return {
        chatState,
        updateChatState,
    }
}

export default useChatState
