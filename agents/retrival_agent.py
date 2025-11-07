import asyncio
from memory import Memory
from agents.agent import Agent
from sqlalchemy.orm import Session
from utility import animate_thinking
from concurrent.futures import ThreadPoolExecutor
from langchain_community.vectorstores import Cassandra
from models import CreatingBot, KnowledgeBase, KBIndexIDs
from langchain_community.embeddings import DeepInfraEmbeddings
from utility import get_table_names
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import func, String
from sqlalchemy import select, exists, literal_column

import config, logging, cassio

log =  logging.getLogger(__name__)
logging.basicConfig(filename="main.log",level=logging.INFO)
cassio.init(token=config.TOKENS["token"], database_id=config.DB_ID)

embeddings = DeepInfraEmbeddings(
    model_id=config.BAAI_MODEL_ID,
    deepinfra_api_token=config.DEEPINFRA_API_TOKEN,
)

class ReterivalAgent(Agent):
    def __init__(self, name, prompt_path, provider, cid, verbose=False):
        """
        The casual agent is a special for casual talk to the user without specific tasks.
        """
        super().__init__(name, prompt_path, provider, verbose, None)
        self.tools = {
        } # No tools for the casual agent
        self.role = "retrive"
        self.type = "retrival_agent"
        self.memory = Memory(self.load_prompt(prompt_path),
                                memory_compression=False,
                                cid=cid,
                                model_provider=provider.get_model_name())
        
    async def retrive_knowledge(self, table_names: list[str], query, top_k:int = 10) -> str:
        try:
            async def run_task(table_name):
                print(f"Searching Vector: {table_name}")
                astra_vector_store = Cassandra(
                    table_name=table_name,
                    embedding=embeddings,
                    session=None,
                    keyspace="default_keyspace",
                )
                # Perform the retrieval by row ID
                result = await astra_vector_store.asimilarity_search(query=query, k=top_k)
                print(f"Result Len: {len(result)}")
                return result

        # Execute tasks concurrently using ThreadPoolExecutor
            query_text = ""
            tasks = [run_task(table_name) for table_name in table_names]
            results = await asyncio.gather(*tasks)
            all_docs=[]
            for result in results:
                if isinstance(result, list):
                    all_docs.extend(result)
                else:
                    log.error(f"Error processing task: {result}")
            print(f"All Docs Len: {len(all_docs)}")
            for res in all_docs:
                print(res)
                query_text = query_text + f"{res}\n"
            print(f"Len of Query Text: {len(query_text)}")
            return query_text
        except Exception as e:
            log.error(f"Error getting chunk from {table_names}: {str(e)}")
            return None
    
    async def process(self, prompt: str, bot_key: str = None, db: Session | None = None) -> str:
        if not bot_key and not db:
            raise "Need DB And Bot key to start retrival"
        myKbs = []
        api = db.query(CreatingBot).filter(CreatingBot.apikey == bot_key).first()
        if api.training_files:
            myKbs = api.training_files.split(",")
        context = ""
        print(myKbs)
        if myKbs:
            myKbIds = [int(i) for i in myKbs]
            print(f"Entering Kb, {myKbIds}")
            data = db.query(KnowledgeBase).filter(KnowledgeBase.id.in_(myKbIds)).all()
            print(len(data))
            doc_names = [d.file_name for d in data if d.file_name is not None]
            print(doc_names)
            K = KBIndexIDs
            elem = func.jsonb_array_elements_text(K.index_ids).table_valued("value", type_=String, joins_implicitly=True)
            subq = (
                select(literal_column("1"))
                .select_from(elem)
                .where(elem.c.value.in_(doc_names))
                .correlate(K)  # ensure the subquery is correlated with KBIndexIDs
            )

            filtered = (
                db.query(KBIndexIDs)
                .filter(exists(subq))
                .all()
            )
            filtered_doc_ids = [str(f.id) for f in filtered]
            filter = {
                "row_id": {
                    "$in": filtered_doc_ids
                }
            }
            kb_ids = list(set(kb.kb_id for kb in data if kb.kb_id is not None))
            print("Getting Table names")
            unique_table_names = await get_table_names(self.orgn, kb_ids, self.uid)
            print(f"Getting context: {unique_table_names}")
            context = await self.retrive_knowledge(unique_table_names, prompt)
            print(f"Context: {context}")
        SYS_PROMPT = """
            You are the best AI assistant designed to answer questions with precision, specificity, and conciseness. Your responses must strictly adhere to the content and question provided by the user.
            Instructions:
                1. Always use the provided content to form your response.
                2. If the provided content does not match or sufficiently address the question, and if web search results are available, incorporate the relevant web search results into your answer.
                3. Do not add extra information, context, or opinions beyond what is explicitly stated in the provided content or verified by the web search results.
                4. Focus on directly addressing the question, staying on topic, and being as clear and concise as possible.
                5. Also consider the prompt given by the user, but do not go beyond the rules above.
        """
        final_query = f"{api.prompt if api.prompt else SYS_PROMPT} \n User Query: {prompt} \n Context: {context}" 
        # self.memory.push('user', final_query)
        self.memory.push('user', final_query, context=context, query=prompt)
        animate_thinking("Thinking...", color="status")
        answer, reasoning = await self.llm_request()
        self.last_answer = answer
        self.status_message = "Ready"
        return answer, reasoning

if __name__ == "__main__":
    from db import SessionLocal
    def get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()
    rag = ReterivalAgent()
    session = get_db()
    rag.process("Ai Agents", "cx-odwb1gA9IRpgcVpk", session)
    