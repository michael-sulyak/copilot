class LLMMessageRoles:
    USER = 'user'
    SYSTEM = 'system'
    ASSISTANT = 'assistant'
    FUNCTION = 'function'


class LLMToolParamTypes:
    STRING = 'string'
    OBJECT = 'object'
    ARRAY = 'array'
    BOOLEAN = 'boolean'


class LLMContentTypes:
    TEXT = 'input_text'
    IMAGE = 'input_image'
    FUNCTION_CALL = 'function_call'
    FUNCTION_CALL_OUTPUT = 'function_call_output'


class LLMReasoningEffort:
    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'


class NOTSET:
    pass
