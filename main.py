from router import AgentRouter
from logger import Logger
from agents import CasualAgent, BrowserAgent, CoderAgent, FileAgent, PlannerAgent, ReterivalAgent
from browser import Browser, create_driver
from llm_provider import Provider
from interaction import Interaction
from dotenv import load_dotenv
from time import sleep
from utility import pretty_print

import configparser
import sys
import os, asyncio

load_dotenv()

def is_running_in_docker():
    """Detect if code is running inside a Docker container."""
    # Method 1: Check for .dockerenv file
    if os.path.exists('/.dockerenv'):
        return True
    
    # Method 2: Check cgroup
    try:
        with open('/proc/1/cgroup', 'r') as f:
            return 'docker' in f.read()
    except:
        pass
    
    return False

config = configparser.ConfigParser()
config.read('config.ini')
logger = Logger("backend.log")

def initialize_system(cid: str):
    stealth_mode = config.getboolean('BROWSER', 'stealth_mode')
    personality_folder = "jarvis" if config.getboolean('MAIN', 'jarvis_personality') else "base"
    languages = config["MAIN"]["languages"].split(' ')
    
    # Force headless mode in Docker containers
    headless = config.getboolean('BROWSER', 'headless_browser')
    if is_running_in_docker() and not headless:
        # Print prominent warning to console (visible in docker-compose output)
        print("\n" + "*" * 70)
        print("*** WARNING: Detected Docker environment - forcing headless_browser=True ***")
        print("*** INFO: To see the browser, run 'python cli.py' on your host machine ***")
        print("*" * 70 + "\n")
        
        # Flush to ensure it's displayed immediately
        sys.stdout.flush()
        
        # Also log to file
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
    browser = Browser(
        create_driver(headless=headless, stealth_mode=stealth_mode, lang=languages[0], port=port),
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

async def main():
    from db import SessionLocal
    def get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()
    session = next(get_db())
    interaction = initialize_system()
    interaction.set_query(query="Current dispute between thailand and combodia", bot_key="cx-odwb1gA9IRpgcVpk", db=session)
    print(f"Starting the questioning: Current dispute between thailand and combodia")
    await interaction.think("ffb76919-3348-53d4-b6f2-203e92277db2", "asklly")
    while True:
        sleep(1)
        if interaction.last_answer:
            print("Answer Generated")
            print("Reasoning: ",interaction.last_reasoning)
            print("Answer: ",interaction.last_answer)
            break
        print("Generating Answer....")

if __name__ == "__main__":
    from tools import braveSearch
    # asyncio.run(main())
    search_tool = braveSearch()
    result = search_tool.execute(["are dog better than cat?"])
    print(result)