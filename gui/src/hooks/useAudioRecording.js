import {useCallback, useEffect, useRef, useState} from 'react'
import {callRpc} from '../api'

function useAudioRecording({addNotification, setInputValue, uploadFiles, updateMessengerState, processRpcError}) {
    const [recordingState, setRecordingState] = useState({status: 'off'})
    const mediaRecorderRef = useRef(null)
    const streamRef = useRef(null)
    const busyRef = useRef(false)
    const mountedRef = useRef(false)

    useEffect(() => {
        mountedRef.current = true
        return () => {
            mountedRef.current = false
            const recorder = mediaRecorderRef.current
            if (recorder) {
                recorder.onstop = null
                if (recorder.state !== 'inactive') recorder.stop()
            }
            streamRef.current?.getTracks().forEach((track) => track.stop())
        }
    }, [])

    const startRecording = useCallback(async () => {
        if (busyRef.current) return
        busyRef.current = true
        try {
            if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
                throw new Error('Audio recording is not supported in this browser. Use HTTPS or localhost.')
            }

            const stream = await navigator.mediaDevices.getUserMedia({audio: true})

            if (!mountedRef.current) {
                stream.getTracks().forEach((track) => track.stop())
                return
            }
            streamRef.current = stream
            const recorder = new MediaRecorder(stream)
            mediaRecorderRef.current = recorder
            const chunks = []
            recorder.ondataavailable = (event) => {
                if (event.data?.size) chunks.push(event.data)
            }
            recorder.onerror = (event) => {
                recorder.onstop = null
                stream.getTracks().forEach((track) => track.stop())
                busyRef.current = false

                if (mountedRef.current) {
                    setRecordingState({status: 'off'})
                    addNotification(event.error?.message || 'Audio recording failed.')
                }
            }

            recorder.onstop = async () => {
                stream.getTracks().forEach((track) => track.stop())
                if (!mountedRef.current) return
                setRecordingState({status: 'processing'})
                try {
                    const mimeType = recorder.mimeType || 'audio/webm'
                    const extension = mimeType.includes('mp4') ? 'mp4' : mimeType.includes('ogg') ? 'ogg' : 'webm'
                    const blob = new Blob(chunks, {type: mimeType})
                    const audio = new File([blob], `recording_${Date.now()}.${extension}`, {type: mimeType})
                    const files = await uploadFiles({files: [audio], updateMessangerStateText: false})
                    updateMessengerState({text: 'Processing audio…'})
                    const result = await callRpc('process_audio', [files[0].id], 120000)
                    if (result?.error) throw new Error(result.error)
                    if (typeof result?.text !== 'string') throw new Error('The server returned an invalid transcription.')
                    if (mountedRef.current) setInputValue((current) => (current ? `${current}\n\n${result.text}` : result.text))
                } catch (error) {
                    if (mountedRef.current) await processRpcError(error)
                } finally {
                    busyRef.current = false
                    if (mountedRef.current) {
                        setRecordingState({status: 'off'})
                        updateMessengerState({text: null})
                    }
                }
            }
            recorder.start()
            setRecordingState({status: 'on', startedAt: new Date()})
        } catch (error) {
            streamRef.current?.getTracks().forEach((track) => track.stop())
            busyRef.current = false
            if (mountedRef.current) {
                setRecordingState({status: 'off'})
                await addNotification(error.message)
            }
        }
    }, [addNotification, setInputValue, uploadFiles, updateMessengerState, processRpcError])

    const stopRecording = useCallback(() => {
        const recorder = mediaRecorderRef.current
        if (recorder?.state === 'recording') recorder.stop()
    }, [])

    return {recordingState, startRecording, stopRecording}
}

export default useAudioRecording
