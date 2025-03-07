import React, {useEffect, useState} from 'react'
import {Button, Toast} from 'react-bootstrap'
import Markdown from './Markdown'

function Notification({notification, onHide}) {
    const [show, setShow] = useState(true)

    useEffect(() => {
        if (!show) {
            setTimeout(onHide, 5000)
        }
    }, [show, onHide])

    return (
        <Toast key={notification.id} show={show} onClose={() => setShow(false)} className={'mt-2'} delay={10000} autohide>
            <div className={'d-flex align-items-center'}>
                <Toast.Body>
                    <Markdown content={notification.content} />
                </Toast.Body>
                <Button variant="primary" className={'btn-close btn-close-white me-2 m-auto'} onClick={() => setShow(false)} />
            </div>
        </Toast>
    )
}

export default Notification
