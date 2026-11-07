import {useCallback, useEffect, useRef, useState} from 'react'
import {apiUrl} from '../api'
import {getUiTimestamp, isImage} from '../utils'

const MAX_FILE_SIZE = 10 * 1024 * 1024
const MAX_TOTAL_SIZE = 50 * 1024 * 1024
const MAX_FILES = 20

function useFileUpload({addNotification, updateMessengerState, activeChatUuid}) {
    const [attachedFiles, setAttachedFiles] = useState([])
    const [isUploading, setIsUploading] = useState(false)
    const attachedFilesRef = useRef([])
    const pendingUploadsRef = useRef(new Set())
    const generationRef = useRef(0)

    const clearFiles = useCallback(() => {
        generationRef.current += 1
        attachedFilesRef.current.forEach((file) => {
            if (file.preview) URL.revokeObjectURL(file.preview)
        })
        attachedFilesRef.current = []
        setAttachedFiles([])
    }, [])

    useEffect(() => {
        clearFiles()
    }, [activeChatUuid, clearFiles])

    useEffect(() => {
        const uploads = pendingUploadsRef.current
        return () => {
            generationRef.current += 1
            uploads.forEach((xhr) => xhr.abort())
            attachedFilesRef.current.forEach((file) => {
                if (file.preview) URL.revokeObjectURL(file.preview)
            })
        }
    }, [])

    const uploadFiles = useCallback(
        async ({files, updateMessangerStateText = true}) => {
            if (
                !files.length ||
                files.length > MAX_FILES ||
                files.some((file) => file.size > MAX_FILE_SIZE) ||
                files.reduce((total, file) => total + file.size, 0) > MAX_TOTAL_SIZE
            ) {
                throw new Error('Upload up to 20 files, at most 10 MiB each and 50 MiB in total.')
            }
            const formData = new FormData()
            files.forEach((file) => formData.append('files', file))
            const xhr = new XMLHttpRequest()
            pendingUploadsRef.current.add(xhr)
            xhr.open('POST', apiUrl('/upload-file'), true)
            xhr.timeout = 120000
            xhr.responseType = 'json'
            setIsUploading(true)
            const progressTimestamp = getUiTimestamp()
            if (updateMessangerStateText) {
                xhr.upload.onprogress = (event) => {
                    if (event.lengthComputable) {
                        updateMessengerState({
                            text: `File uploading… (${Math.round((event.loaded / event.total) * 100)}%)`,
                            timestamp: progressTimestamp,
                        })
                    }
                }
            }
            try {
                return await new Promise((resolve, reject) => {
                    xhr.onload = () => {
                        if (xhr.status < 200 || xhr.status >= 300) {
                            reject(new Error(`Upload failed (HTTP ${xhr.status}).`))
                        } else if (!Array.isArray(xhr.response?.files) || xhr.response.files.length !== files.length) {
                            reject(new Error('The server returned an invalid upload response.'))
                        } else {
                            resolve(xhr.response.files)
                        }
                    }
                    xhr.onerror = () => reject(new Error('Upload failed. Check the server connection.'))
                    xhr.ontimeout = () => reject(new Error('Upload timed out. Please try again.'))
                    xhr.onabort = () => reject(new Error('Upload cancelled.'))
                    xhr.send(formData)
                })
            } finally {
                pendingUploadsRef.current.delete(xhr)
                setIsUploading(pendingUploadsRef.current.size > 0)
                if (updateMessangerStateText) {
                    updateMessengerState({text: null, timestamp: progressTimestamp})
                }
            }
        },
        [updateMessengerState]
    )

    const onFileUpload = async (event) => {
        const files = Array.from(event.target.files ?? [])
        if (!files.length) return
        const generation = generationRef.current
        try {
            if (attachedFilesRef.current.length + files.length > MAX_FILES) {
                throw new Error('A message can have at most 20 attachments.')
            }
            const uploadedFiles = await uploadFiles({files})
            if (generation !== generationRef.current) return
            if (attachedFilesRef.current.length + files.length > MAX_FILES) {
                throw new Error('A message can have at most 20 attachments.')
            }
            const newFiles = files.map((file, index) => ({
                ...uploadedFiles[index],
                preview: isImage(file.name) ? URL.createObjectURL(file) : null,
                type: file.type,
            }))
            attachedFilesRef.current = [...attachedFilesRef.current, ...newFiles]
            setAttachedFiles(attachedFilesRef.current)
        } catch (error) {
            await addNotification(error.message)
        } finally {
            if ('value' in event.target) event.target.value = ''
        }
    }

    const removeAttachedFile = useCallback((fileId) => {
        const removed = attachedFilesRef.current.find((file) => file.id === fileId)
        if (removed?.preview) URL.revokeObjectURL(removed.preview)
        attachedFilesRef.current = attachedFilesRef.current.filter((file) => file.id !== fileId)
        setAttachedFiles(attachedFilesRef.current)
    }, [])

    return {attachedFiles, isUploading, onFileUpload, removeAttachedFile, clearFiles, uploadFiles}
}

export default useFileUpload
