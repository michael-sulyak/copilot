class GPTRoles:
    USER = 'user'
    SYSTEM = 'system'
    ASSISTANT = 'assistant'
    FUNCTION = 'function'


class GPTFuncParamTypes:
    STRING = 'string'
    OBJECT = 'object'


class GPTContentTypes:
    TEXT = 'text'
    IMAGE_URL = 'image_url'
    FUNCTION = 'function'


class GPTResponseFormat:
    TEXT = 'text'
    JSON_OBJECT = 'json_object'


class GPTReasoningEffort:
    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'


class NOTSET:
    pass


class GPTBehaviour:
    # Generates text that adheres to established patterns and conventions.
    # Output is more deterministic and focused. Useful for generating syntactically correct text.
    FORMAL = {'temperature': 0.2, 'top_p': 0.1}

    # Generates creative and diverse text for storytelling.
    # Output is more exploratory and less constrained by patterns.
    CREATIVE = {'temperature': 0.7, 'top_p': 0.8}

    # Generates conversational responses that balance coherence and diversity.
    # Output is more natural and engaging.
    CONVERSATIONAL = {'temperature': 0.5, 'top_p': 0.5}

    # Generates text that is more likely to be concise and relevant.
    # Output is more deterministic and adheres to conventions.
    CONCISE = {'temperature': 0.3, 'top_p': 0.2}

    # Generates analytical text that is more likely to be correct and efficient.
    # Output is more deterministic and focused.
    ANALYTICAL = {'temperature': 0.2, 'top_p': 0.1}

    # Generates text that explores alternative solutions and creative approaches.
    # Output is less constrained by established patterns.
    EXPLORATORY = {'temperature': 0.6, 'top_p': 0.7}
