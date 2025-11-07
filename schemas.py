from typing import Optional
from pydantic import BaseModel
from utility import pretty_print

class QueryRequest(BaseModel):
    query: str
    bot_key: str
    org: str
    uid: str
    cid: Optional[str] = None


class QueryResponse(BaseModel):
    done: str
    answer: str
    reasoning: str
    agent_name: str
    success: str
    blocks: dict
    status: str
    uid: str

    def __str__(self):
        return f"Done: {self.done}, Answer: {self.answer}, Agent Name: {self.agent_name}, Success: {self.success}, Blocks: {self.blocks}, Status: {self.status}, UID: {self.uid}"

    def jsonify(self):
        return {
            "done": self.done,
            "answer": self.answer,
            "reasoning": self.reasoning,
            "agent_name": self.agent_name,
            "success": self.success,
            "blocks": self.blocks,
            "status": self.status,
            "uid": self.uid
        }

class executorResult:
    """
    A class to store the result of a tool execution.
    """
    def __init__(self, block: str, feedback: str, success: bool, tool_type: str):
        """
        Initialize an agent with execution results.

        Args:
            block: The content or code block processed by the agent.
            feedback: Feedback or response information from the execution.
            success: Boolean indicating whether the agent's execution was successful.
            tool_type: The type of tool used by the agent for execution.
        """
        self.block = block
        self.feedback = feedback
        self.success = success
        self.tool_type = tool_type
    
    def __str__(self):
        return f"Tool: {self.tool_type}\nBlock: {self.block}\nFeedback: {self.feedback}\nSuccess: {self.success}"
    
    def jsonify(self):
        return {
            "block": self.block,
            "feedback": self.feedback,
            "success": self.success,
            "tool_type": self.tool_type
        }

    def show(self):
        pretty_print('▂'*64, color="status")
        pretty_print(self.feedback, color="success" if self.success else "failure")
        pretty_print('▂'*64, color="status")

class ResponseModel(BaseModel):
    status: str
    status_message: str
    answer: str
    tool_calls: list[str]

class ImageData(BaseModel):
    filename: str
    base64_data: str
    dir: Optional[bool] = False

class ChatRequest(BaseModel):
    question: str
    kbs: str
    orgn: str
    cid:  str | None = None
    uid: str
    image: str | None = None
    drive: str | None = None
    search: Optional[bool] = False

class OneDrive(BaseModel):
    name: str
    web_url: str
    mime_type: str = None
    file_id: str = None

class ApiRequest(BaseModel):
    question: str
    api: str
    cid:  str | None = None
    uid: str
    image: Optional[str] = None
    drive: Optional[str] = None
    search: Optional[bool] = False
    onedrive: Optional[list[OneDrive]] = None

class MobileApiRequest(BaseModel):
    question: str
    api: str
    cid: str
    uid: str
    image: str | None = None
    drive: str | None = None
    token: str
    search: bool = False
    onedrive: Optional[list[OneDrive]] = None

class StockApiRequest(BaseModel):
    question: str
    api: str
    cid: str
    uid: str
    image: str

class ReApiRequest(BaseModel):
    question: str
    api: str
    cid: str
    uid: str
    image: str | None = None
    drive: str | None = None
    token: str | None = None
    search: bool = False
    onedrive: Optional[list[OneDrive]] = None

class MobileReApiRequest(BaseModel):
    question: str
    api: str
    cid: str
    uid: str
    image: str | None = None
    drive: str | None = None
    search: bool = False
    onedrive: Optional[list[OneDrive]] = None

class DocsRequest(BaseModel):
    question: str
    api: str

class HistoryRequest(BaseModel):
    uid: str