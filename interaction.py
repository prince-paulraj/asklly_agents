import readline
from typing import List, Tuple, Type, Dict
from sqlalchemy.orm import Session
from text_to_speech import Speech
from utility import pretty_print, animate_thinking
from router import AgentRouter
from speech_to_text import AudioTranscriber, AudioRecorder
import asyncio


class Interaction:
    """
    Interaction is a class that handles the interaction between the user and the agents.
    """
    def __init__(self, agents,
                 tts_enabled: bool = True,
                 stt_enabled: bool = True,
                 recover_last_session: bool = False,
                 langs: List[str] = ["en", "zh"]
                ):
        self.is_active = True
        self.current_agent = None
        self.last_query = None
        self.last_answer = None
        self.last_reasoning = None
        self.agents = agents
        self.tts_enabled = tts_enabled
        self.stt_enabled = stt_enabled
        self.recover_last_session = recover_last_session
        self.router = AgentRouter(self.agents, supported_language=langs)
        self.ai_name = self.find_ai_name()
        self.speech = None
        self.transcriber = None
        self.recorder = None
        self.is_generating = False
        self.languages = langs
        self.bot_key = None
        self.browser_sources = None
        self.last_answer = None
        self.last_browser_search = None
        self.browser_agent = next((agent for agent in self.agents if agent.type == "browser_agent"), None)
        self.db: Session | None = None
        if tts_enabled:
            self.initialize_tts()
        if stt_enabled:
            self.initialize_stt()
        if recover_last_session:
            self.load_last_session()
        self.emit_status()
    
    def get_spoken_language(self) -> str:
        """Get the primary TTS language."""
        lang = self.languages[0]
        return lang

    def initialize_tts(self):
        """Initialize TTS."""
        if not self.speech:
            animate_thinking("Initializing text-to-speech...", color="status")
            self.speech = Speech(enable=self.tts_enabled, language=self.get_spoken_language(), voice_idx=1)

    def initialize_stt(self):
        """Initialize STT."""
        if not self.transcriber or not self.recorder:
            animate_thinking("Initializing speech recognition...", color="status")
            self.transcriber = AudioTranscriber(self.ai_name, verbose=False)
            self.recorder = AudioRecorder()
    
    def emit_status(self):
        """Print the current status of asklly."""
        if self.stt_enabled:
            pretty_print(f"Text-to-speech trigger is {self.ai_name}", color="status")
        if self.tts_enabled:
            self.speech.speak("Hello, we are online and ready. What can I do for you ?")
        pretty_print("asklly is ready.", color="status")
    
    def find_ai_name(self) -> str:
        """Find the name of the default AI. It is required for STT as a trigger word."""
        ai_name = "jarvis"
        for agent in self.agents:
            if agent.type == "casual_agent":
                ai_name = agent.agent_name
                break
        return ai_name
    
    def get_last_blocks_result(self) -> List[Dict]:
        """Get the last blocks result."""
        if self.current_agent is None:
            return []
        blks = []
        for agent in self.agents:
            blks.extend(agent.get_blocks_result())
        return blks
    
    def load_last_session(self):
        """Recover the last session."""
        for agent in self.agents:
            if agent.type == "planner_agent":
                continue
            agent.memory.load_memory(agent.type)
    
    def save_session(self):
        """Save the current session."""
        for agent in self.agents:
            agent.memory.save_memory(agent.type)

    def is_active(self) -> bool:
        return self.is_active
    
    def read_stdin(self) -> str:
        """Read the input from the user."""
        buffer = ""

        PROMPT = "\033[1;35m➤➤➤ \033[0m"
        while not buffer:
            try:
                buffer = input(PROMPT)
            except EOFError:
                return None
            if buffer == "exit" or buffer == "goodbye":
                return None
        return buffer
    
    async def transcription_job(self) -> str:
        """Transcribe the audio from the microphone."""
        self.recorder = AudioRecorder(verbose=True)
        self.transcriber = AudioTranscriber(self.ai_name, verbose=True)
        self.transcriber.start()
        self.recorder.start()
        while self.recorder.is_alive() and self.transcriber.is_alive():
            await asyncio.sleep(0.1)
        query = self.transcriber.get_transcript()
        if query == "exit" or query == "goodbye":
            return None
        return query

    async def get_user(self) -> str:
        """Get the user input from the microphone or the keyboard."""
        if self.stt_enabled:
            query = "TTS transcription of user: " + await self.transcription_job()
        else:
            query = self.read_stdin()
        if query is None:
            self.is_active = False
            self.last_query = None
            return None
        self.last_query = query
        return query
    
    def set_query(self, query: str, bot_key: str = None, db: Session = None) -> None:
        """Set the query"""
        self.bot_key = bot_key
        self.is_active = True
        self.last_query = query
        self.db = db

    async def think(self, uid, org) -> bool:
        """Request AI agents to process the user input."""
        push_last_agent_memory = False
        if self.last_query is None or len(self.last_query) == 0:
            return False
        agent = await asyncio.to_thread(self.router.select_agent, self.last_query)
        if agent is None:
            return False
        agent.set_org(org, uid)
        if self.current_agent != agent and self.last_answer is not None:
            push_last_agent_memory = True
        tmp = self.last_answer
        pretty_print(f"Selected :{agent.agent_name} bot key :{self.bot_key}", color="success")
        self.current_agent = agent
        self.is_generating = True
        if agent.agent_name == "retrieval":
            retrieval_answer, retrieval_reasoning = await agent.process(self.last_query, bot_key=self.bot_key, db=self.db)
            self.last_answer = retrieval_answer
            self.last_reasoning = retrieval_reasoning
        else:
            self.last_answer, self.last_reasoning = await agent.process(self.last_query, self.speech)
        self.is_generating = False
        if push_last_agent_memory:
            self.current_agent.memory.push('assistant', self.last_answer)
        if self.last_answer == tmp:
            self.last_answer = None
        return True
    
    def get_updated_process_answer(self) -> str:
        """Get the answer from the last agent."""
        if self.current_agent is None:
            return None
        return self.current_agent.get_last_answer()
    
    def get_updated_block_answer(self) -> str:
        """Get the answer from the last agent."""
        if self.current_agent is None:
            return None
        return self.current_agent.get_last_block_answer()
    
    async def speak_answer(self) -> None:
        """Speak the answer to the user in a non-blocking thread."""
        if self.last_query is None:
            return
        if self.tts_enabled and self.last_answer and self.speech:
            await asyncio.to_thread(self.speech.speak, self.last_answer)
    
    def show_answer(self) -> None:
        """Show the answer to the user."""
        if self.last_query is None:
            return
        if self.current_agent is not None:
            self.current_agent.show_answer()

