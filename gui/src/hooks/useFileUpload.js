import {useCallback, useState} from 'react'
import {getTimestampNs, isImage} from '../utils'

const MAX_FILE_SIZE = 10 * 1024 * 1024 // 10 MB

function useFileUpload({addNotification, updateChatState}) {
    const [attachedFiles, setAttachedFiles] = useState([])

    const clearFiles = useCallback(() => {
        attachedFiles.forEach((file) => {
            if (file.preview) URL.revokeObjectURL(file.preview)
        })
        setAttachedFiles([])
    }, [attachedFiles])

    const uploadFiles = useCallback(
        async ({files, updateChatStateText = true, callback}) => {
            const formData = new FormData()
            files.forEach((file) => {
                formData.append('files', file)
            })

            const xhr = new XMLHttpRequest()
            xhr.open('POST', 'http://localhost:8123/upload-file', true)

            if (updateChatStateText) {
                xhr.upload.onprogress = async (event) => {
                    if (event.lengthComputable) {
                        const percentComplete = Math.round((event.loaded / event.total) * 100)
                        await updateChatState({text: `File uploading... (${percentComplete}%)`})
                    }
                }
            }

            xhr.onload = async () => {
                const timestamp = getTimestampNs()

                if (updateChatStateText) {
                    if (xhr.status === 200) {
                        await updateChatState({text: 'Files uploaded successfully', timestamp})
                    } else {
                        await updateChatState({text: 'Failed to upload files', timestamp})
                    }

                    setTimeout(() => {
                        updateChatState({text: null, timestamp: timestamp + 1})
                    }, 2000)
                } else if (xhr.status !== 200) {
                    await addNotification('Failed to upload files')
                }
            }

            xhr.onreadystatechange = () => {
                if (xhr.readyState === 4) {
                    if (callback) {
                        callback(xhr.response)
                    }
                }
            }
            xhr.send(formData)
        },
        [addNotification, updateChatState]
    )

    const onFileUpload = async (e) => {
        if (!e.target.files) {
            return
        }

        const files = Array.from(e.target.files)
        const validFiles = files.filter((file) => file.size <= MAX_FILE_SIZE)

        console.log(files)

        if (validFiles.length !== files.length) {
            await addNotification(`Some files were not uploaded due to size.\nMax size: ${MAX_FILE_SIZE / 1024 / 1024} Mb.`)
            return
        }

        await uploadFiles({
            files: validFiles,
            callback: async (response) => {
                const uploadedFiles = JSON.parse(response).files
                console.log({uploadedFiles})

                const imageUrls = files.map((file) => URL.createObjectURL(file))

                const newFiles = files.map((file, index) => ({
                    ...uploadedFiles[index],
                    preview: isImage(file.name) ? imageUrls[index] : null,
                    type: file.type,
                }))

                await setAttachedFiles((prevFiles) => [...prevFiles, ...newFiles])
                // await addNotification(`Uploaded ${validFiles.map((file) => file.name).join(', ')}`)
            },
        })
    }

    const removeAttachedFile = useCallback((fileId) => {
        setAttachedFiles((prev) =>
            prev.filter((file) => {
                if (file.id === fileId) {
                    file.preview && URL.revokeObjectURL(file.preview)
                    return false
                }
                return true
            })
        )
    }, [])

    return {attachedFiles, onFileUpload, removeAttachedFile, clearFiles, uploadFiles}
}

export default useFileUpload
