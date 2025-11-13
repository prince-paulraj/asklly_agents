from typing import Dict
from interaction import Interaction
import time, logging
import asyncio
from router import AgentRouter
from logger import Logger
from agents import CasualAgent, BrowserAgent, CoderAgent, FileAgent, PlannerAgent, ReterivalAgent
from browser import Browser, create_driver
from llm_provider import Provider
from dotenv import load_dotenv
import configparser
import sys
import os

load_dotenv()

def is_running_in_docker():
    """Detect if code is running inside a Docker container."""
    if os.path.exists('/.dockerenv'):
        return True
    
    try:
        with open('/proc/1/cgroup', 'r') as f:
            return 'docker' in f.read()
    except:
        pass
    
    return False

config = configparser.ConfigParser()
config.read('config.ini')
logger = Logger("backend.log")

async def initialize_system(cid: str):
    stealth_mode = config.getboolean('BROWSER', 'stealth_mode')
    personality_folder = "jarvis" if config.getboolean('MAIN', 'jarvis_personality') else "base"
    languages = config["MAIN"]["languages"].split(' ')
    
    headless = config.getboolean('BROWSER', 'headless_browser')
    if is_running_in_docker() and not headless:
        print("\n" + "*" * 70)
        print("*** WARNING: Detected Docker environment - forcing headless_browser=True ***")
        print("*** INFO: To see the browser, run 'python cli.py' on your host machine ***")
        print("*" * 70 + "\n")
        
        sys.stdout.flush()
        
        logger.warning("Detected Docker environment - forcing headless_browser=True")
        logger.info("To see the browser, run 'python cli.py' on your host machine instead")
        
        headless = True
    
    provider = Provider(
        provider_name=config["MAIN"]["provider_name"],
        model=config["MAIN"]["provider_model"],
        server_address=config["MAIN"]["provider_server_address"],
        is_local=config.getboolean('MAIN', 'is_local')
    )
    logger.info(f"Provider initialized: {provider.provider_name} ({provider.model})")

    import random
    port = random.randint(10000, 65535)
    driver = await asyncio.to_thread(create_driver, headless=headless, stealth_mode=stealth_mode, lang=languages[0], port=port)
    browser = Browser(
        driver,
        anticaptcha_manual_install=stealth_mode
    )
    logger.info("Browser initialized")

    agents = [
        CasualAgent(
            name=config["MAIN"]["agent_name"],
            prompt_path=f"prompts/{personality_folder}/casual_agent.txt",
            provider=provider, verbose=False, cid=cid
        ),
        CoderAgent(
            name="coder",
            prompt_path=f"prompts/{personality_folder}/coder_agent.txt",
            provider=provider, verbose=False, cid=cid
        ),
        ReterivalAgent(
            name="retrieval",
            prompt_path=f"prompts/{personality_folder}/retrival_agent.txt",
            provider=provider, verbose=False, cid=cid
        ),
        BrowserAgent(
            name="Browser",
            prompt_path=f"prompts/{personality_folder}/browser_agent.txt",
            provider=provider, verbose=False, browser=browser, cid=cid
        ),
        PlannerAgent(
            name="Planner",
            prompt_path=f"prompts/{personality_folder}/planner_agent.txt",
            provider=provider, verbose=False, browser=browser, cid=cid
        )
    ]
    logger.info("Agents initialized")

    interaction = Interaction(
        agents,
        tts_enabled=config.getboolean('MAIN', 'speak'),
        stt_enabled=config.getboolean('MAIN', 'listen'),
        recover_last_session=config.getboolean('MAIN', 'recover_last_session'),
        langs=languages
    )
    logger.info("Interaction initialized")
    return interaction

log = logging.getLogger(__name__)

class SessionManager:
    def __init__(self, session_timeout: int = 1800):
        self.sessions: Dict[str, Interaction] = {}
        self.session_timeout = session_timeout
        self._lock = asyncio.Lock()

    async def get_session(self, cid: str) -> Interaction:
        async with self._lock:
            if cid not in self.sessions:
                log.info(f"Creating new session for cid: {cid}")
                self.sessions[cid] = await initialize_system(cid)
            else:
                log.info(f"Reusing existing session for cid: {cid}")
            
            self.sessions[cid].last_active_time = time.time()
            return self.sessions[cid]

    async def cleanup_sessions(self):
        while True:
            await asyncio.sleep(60)
            now = time.time()
            
            async with self._lock:
                inactive_sessions = [
                    cid for cid, session in self.sessions.items()
                    if now - session.last_active_time > self.session_timeout
                ]
                
                for cid in inactive_sessions:
                    log.info(f"Closing inactive session for cid: {cid}")
                    if cid in self.sessions:
                        self.sessions[cid].close()
                        del self.sessions[cid]

session_manager = SessionManager()