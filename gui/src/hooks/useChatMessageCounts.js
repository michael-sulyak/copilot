import {useMemo} from 'react'

// Count the history already held by the GUI; tool traces and actions are not messages.
function useChatMessageCounts({messagesByChatUuid}) {
    return useMemo(
        () =>
            Object.fromEntries(
                Object.entries(messagesByChatUuid).map(([chatUuid, history]) => [
                    chatUuid,
                    history.filter((message) => (message.from === 'user' && !message.body?.callback) || message.type === 'message').length,
                ])
            ),
        [messagesByChatUuid]
    )
}

export default useChatMessageCounts
