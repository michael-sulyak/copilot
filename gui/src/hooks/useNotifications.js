import {useState, useCallback} from 'react'
import {v4 as uuidv4} from 'uuid'

function useNotifications() {
    const [notifications, setNotifications] = useState([])

    const addNotification = useCallback((message) => {
        setNotifications((prev) => [...prev, {id: uuidv4(), content: message}])
    }, [])

    const removeNotification = useCallback((id) => {
        setNotifications((prev) => prev.filter((notification) => notification.id !== id))
    }, [])

    return {notifications, addNotification, removeNotification}
}

export default useNotifications
