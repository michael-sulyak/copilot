import {useCallback, useEffect, useState} from 'react'

function useSettings({addNotification, processRpcError}) {
    const [settings, setSettings] = useState({})

    const getSettings = useCallback(
        async ({callback = null}) => {
            const rpcClient = window.rpcClient

            try {
                const newSettings = await rpcClient.call('get_settings', []).catch(processRpcError)

                if (!newSettings) {
                    return
                }

                setSettings(newSettings)
                console.log('Settings:', newSettings)

                if (callback) {
                    callback(newSettings)
                }
            } catch (err) {
                addNotification('Error fetching settings: ' + err)
            }
        },
        [addNotification, processRpcError]
    )

    useEffect(() => {
        getSettings({})
    }, [getSettings])

    return {settings, getSettings}
}

export default useSettings
