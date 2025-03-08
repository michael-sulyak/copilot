import {useCallback, useEffect, useState} from 'react'

function useSettings({addNotification}) {
    const [settings, setSettings] = useState({})
    const rpcClient = window.rpcClient

    const getSettings = useCallback(async () => {
        try {
            const newSettings = await rpcClient.call('get_settings', [])
            setSettings(newSettings)
            console.log('Settings:', newSettings)
        } catch (err) {
            addNotification('Error fetching settings: ' + err)
        }
    }, [rpcClient, addNotification])

    useEffect(() => {
        getSettings()
    }, [getSettings])

    return {settings, getSettings}
}

export default useSettings
