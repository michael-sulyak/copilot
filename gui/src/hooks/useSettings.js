import {useCallback, useEffect, useState} from 'react'

function useSettings({addNotification, processRpcError}) {
    const [settings, setSettings] = useState({})

    const getSettings = useCallback(async () => {
        const rpcClient = window.rpcClient

        try {
            const newSettings = await rpcClient.call('get_settings', []).catch(processRpcError)
            setSettings(newSettings)
            console.log('Settings:', newSettings)
        } catch (err) {
            addNotification('Error fetching settings: ' + err)
        }
    }, [addNotification, processRpcError])

    useEffect(() => {
        getSettings()
    }, [getSettings])

    return {settings, getSettings}
}

export default useSettings
