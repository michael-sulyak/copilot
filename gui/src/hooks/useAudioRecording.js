import {useCallback, useRef, useState} from 'react'
import {getTimestampNs} from '../utils'

function useAudioRecording({addNotification, inputValue, setInputValue, uploadFiles, updateChatState}) {
    const [recordingState, setRecordingState] = useState({status: 'off'})
    const mediaRecorderRef = useRef(null)

    const startRecording = useCallback(async () => {
        if (recordingState.status !== 'off') return

        let stream

        try {
            stream = await navigator.mediaDevices.getUserMedia({audio: true})
        } catch (err) {
            addNotification('Error accessing microphone: ' + err.message)
            return
        }

        setRecordingState({status: 'on', startedAt: new Date()})

        const mediaRecorder = new MediaRecorder(stream)
        mediaRecorderRef.current = mediaRecorder
        let chunks = []

        mediaRecorder.ondataavailable = (event) => {
            if (event.data && event.data.size > 0) {
                chunks.push(event.data)
            }
        }

        mediaRecorder.onstop = async () => {
            setRecordingState({status: 'processing'})
            const blob = new Blob(chunks, {type: 'audio/webm'})
            stream.getTracks().forEach((track) => track.stop())
            const fileName = `recording_${Date.now()}.webm`
            const audioFile = new File([blob], fileName, {type: blob.type})

            await uploadFiles({
                files: [audioFile],
                updateChatStateText: false,
                callback: async (response) => {
                    const rpcClient = window.rpcClient

                    const parsedResponse = JSON.parse(response)
                    const uploadedFiles = parsedResponse.files

                    await updateChatState({text: 'Processing audio...', timestamp: getTimestampNs()})
                    const result = await rpcClient.call('process_audio', [uploadedFiles[0].id])

                    setRecordingState({status: 'off'})
                    await updateChatState({text: null, timestamp: getTimestampNs()})

                    if (result.error) {
                        await addNotification(result.error)
                    } else {
                        await setInputValue(inputValue ? `${inputValue}\n\n${result.text}` : result.text)
                    }
                },
            })
        }

        mediaRecorder.start()
    }, [inputValue, updateChatState, recordingState, addNotification, setInputValue, uploadFiles])

    const stopRecording = useCallback(async () => {
        if (mediaRecorderRef.current && recordingState.status === 'on') {
            mediaRecorderRef.current.stop()
        } else {
            addNotification('Not currently recording.')
        }
    }, [recordingState, addNotification])

    return {recordingState, startRecording, stopRecording}
}

export default useAudioRecording
