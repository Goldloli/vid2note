from pydantic import BaseModel, Field
from vid2note_core.agents.models import AgentCapabilities, AgentRun, AgentSession, DetectionResult


class RuntimeResponse(BaseModel):
    id: str
    label: str
    detection: DetectionResult
    capabilities: AgentCapabilities


class CreateAgentSessionRequest(BaseModel):
    runtime_id: str
    model: str | None = None
    context_paths: list[str] = Field(default_factory=list, max_length=18)


class AgentMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=100_000)


class AgentSessionResponse(AgentSession):
    pass


class AgentRunResponse(AgentRun):
    pass
