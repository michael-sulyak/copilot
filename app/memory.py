import abc

from .dialogs.base import Roles
from .models.openai.base import GPTMessage


class BaseMemory(abc.ABC):
    def add_context(self, message: GPTMessage) -> None:
        pass

    def add_message(self, message: GPTMessage) -> None:
        pass

    def pop_message(self) -> GPTMessage:
        pass

    def get_buffer(self) -> list[GPTMessage]:
        pass

    def clear(self) -> None:
        pass


class Memory(BaseMemory):
    _max_user_messages: int
    _messages: list[GPTMessage]
    _count_of_user_messages: int = 0
    _context: GPTMessage | None = None

    def __init__(self, *, max_user_messages: int) -> None:
        self._max_user_messages = max_user_messages
        self._messages = []

    def add_context(self, message: GPTMessage) -> None:
        self._context = message

    def add_message(self, message: GPTMessage) -> None:
        self._messages.append(message)

        if message.role == Roles.USER:
            self._count_of_user_messages += 1

            if self._count_of_user_messages > self._max_user_messages:
                self._reduce_messages()

    def pop_message(self) -> GPTMessage:
        if self._messages[-1].role == Roles.USER:
            self._count_of_user_messages -= 1

        return self._messages.pop()

    def get_buffer(self) -> list[GPTMessage]:
        if self._context:
            return [self._context, *self._messages]

        return self._messages

    def clear(self) -> None:
        self._messages.clear()
        self._count_of_user_messages = 0

    def _reduce_messages(self) -> None:
        first_message_index = None
        remove_before = None
        for i, message in enumerate(self._messages):
            if message.role == Roles.USER:
                if first_message_index is None:
                    first_message_index = i
                else:
                    remove_before = i
                    break

        self._messages = self._messages[remove_before:]
        self._count_of_user_messages -= 1

# class FactualMemory(BaseMemory):
#     def __init__(self, file_path):
#         self.file_path = Path(file_path)
#         self.memory = self.load_memory()
#
#     def load_memory(self):
#         if self.file_path.exists():
#             with open(self.file_path, 'r') as file:
#                 return json.load(file)
#         else:
#             return {"facts": {}}
#
#     def remember_fact(self, key, value):
#         self.memory["facts"][key] = value
#         self.save_memory()
#
#     def recall_fact(self, key):
#         return self.memory["facts"].get(key, None)
#
#     def forget_fact(self, key):
#         if key in self.memory["facts"]:
#             del self.memory["facts"][key]
#             self.save_memory()
#
#     def forget_all_facts(self):
#         self.memory["facts"] = {}
#         self.save_memory()
#
#     def save_memory(self):
#         with open(self.file_path, 'w') as file:
#             json.dump(self.memory, file, indent=4)
