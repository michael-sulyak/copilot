import {useCallback, useEffect, useState} from 'react'
import {callRpc, subscribeConnection} from '../api'

function useSettings({processRpcError}) {
    const [settings, setSettings] = useState({})

    const getSettings = useCallback(
        async ({callback = null} = {}) => {
            try {
                const newSettings = await callRpc('get_settings')

                if (!newSettings) {
                    return
                }

                if (newSettings.protocol_version !== 1) {
                    throw new Error('GUI/backend protocol mismatch. Rebuild the GUI and restart the backend together.')
                }
                setSettings(newSettings)

                if (callback) {
                    callback(newSettings)
                }
            } catch (err) {
                await processRpcError(err)
            }
        },
        [processRpcError]
    )

    useEffect(() => {
        const refresh = () => {
            if (window.rpcClient.ready) getSettings()
        }
        refresh()
        return subscribeConnection(refresh)
    }, [getSettings])

    return {settings, getSettings}
}

export default useSettings
