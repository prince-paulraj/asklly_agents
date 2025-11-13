from openai import OpenAI
from bs4 import BeautifulSoup
from datetime import datetime
from fake_useragent import UserAgent
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import config
import logging
import requests
import random
import time
import logging

log = logging.getLogger(__name__)
logging.basicConfig(filename="main.log", level=logging.INFO)

openai = OpenAI(
    api_key=config.DEEPINFRA_API_TOKEN,
    base_url="https://api.deepinfra.com/v1/openai",
)

class Websearch:
    # Initialize user agent generator at class level
    _ua = UserAgent()
    
    @staticmethod
    def generate_search_query(question: str) -> str:
        """
        Uses OpenAI API to generate a concise search query from a verbose question.
        """
        try:
            today = datetime.now().isoformat()
            system_prompt = (
                f"""
                    You are a helpful assistant that transforms long, detailed questions into short, precise web search queries.
                    Today's date is {today}.
                    Use any available image or analysis context to improve relevance.
                    You may include relevant website names in the query if it improves precision, but do not generate or suggest any URLs.
                    Respond with only the final concise search query — no explanations, no punctuation, and no extra text.
                """
            )

            user_prompt = f"Convert the following question into a concise web search query (only needed one query):\n\n{question}"

            response = openai.chat.completions.create(
                model=config.VISION_MODEL_ID,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2,
                max_tokens=50
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            print(f"OpenAI API error: {e}")
            return ""

    @staticmethod
    def search_web(query, limit=10, max_tokens=80000) -> dict:
        """
        Search the web and return summarized content fitting within the context limit.
        """
        try:
            formatted_query = Websearch.generate_search_query(query)
            log.info(f"Formatted query: {formatted_query}")
            print(formatted_query)
            headers = {
                "Accept": "application/json",
                "X-Subscription-Token": config.BRAVE_API_KEY
            }

            response = requests.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": formatted_query, "count": limit},
                headers=headers
            )

            if not response.ok:
                raise Exception(f"HTTP error {response.status_code}")

            data = response.json()
            web_search_results = []
            urls_seen = set()
            profiles = []

            total_tokens = 0

            for result in data.get("web", {}).get("results", []):
                url = result.get("url")
                if not url or url in urls_seen:
                    continue

                urls_seen.add(url)
                print(f'{len(urls_seen)}/{len(data.get("web", {}).get("results", []))}')
                
                # Add small delay between requests to be polite
                time.sleep(random.uniform(0.5, 1.5))
                
                page_content = Websearch.get_page_content(url, max_tokens)

                if page_content.startswith("Error") or page_content.startswith("Timeout"):
                    continue

                content_tokens = len(page_content) // 4
                if total_tokens + content_tokens > max_tokens:
                    break

                total_tokens += content_tokens
                trimmed_profile = {
                    "title": result.get("title"),
                    "description": result.get("description"),
                    "url": result.get("url"),
                    "profile": {
                        "img": result.get("profile", {}).get("img")
                    }
                }

                profiles.append(trimmed_profile)
                web_search_results.append(
                    f"<source>{url}</source>\n<page_content>\n{page_content}\n</page_content>"
                )

            log.info(f"==========Profiles fetched: {len(profiles)}==========")
            formatted_search_results = "\n".join(web_search_results)
            return {"result": formatted_search_results, "profiles": profiles}

        except Exception as e:
            log.exception(f"Exception in search_web: {str(e)}")
            return {"result": "", "profiles": []}

    @staticmethod
    def _get_browser_headers(referer=None):
        """
        Generate realistic browser headers to avoid detection.
        """
        headers = {
            "User-Agent": Websearch._ua.random,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
            "sec-ch-ua": '"Google Chrome";v="141", "Chromium";v="141", "Not=A?Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"'
        }
        
        if referer:
            headers["Referer"] = referer
        
        return headers

    @staticmethod
    def _create_robust_session():
        """
        Create a requests session with retry strategy.
        """
        session = requests.Session()
        
        # Setup retry strategy for temporary failures
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session

    @staticmethod
    def get_page_content(url, max_tokens, referer="https://www.google.com/"):
        """
        Extracts text content from a given URL with enhanced 403 protection.
        
        Args:
            url: The URL to scrape
            max_tokens: Maximum token limit
            referer: Referer header (default: Google)
        """
        session = None
        try:
            # Create session with retry logic
            session = Websearch._create_robust_session()
            
            # Get realistic headers
            headers = Websearch._get_browser_headers(referer=referer)
            
            token_len = int(max_tokens / 10)
            log.info(f"==========Token Len: {token_len}==========")
            
            # Make request with enhanced headers
            response = session.get(
                url, 
                headers=headers,
                timeout=15,  # Increased timeout
                allow_redirects=True
            )
            response.raise_for_status()

            # Parse content
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Remove unwanted elements
            for element in soup(['script', 'style', 'header', 'footer', 'nav', 'iframe', 'noscript']):
                element.decompose()

            # Extract text
            text_content = soup.get_text(separator='\n').strip()
            
            # Clean up whitespace
            lines = [line.strip() for line in text_content.splitlines() if line.strip()]
            text_content = '\n'.join(lines)
            
            # Tokenize and limit
            words = text_content.split()
            words = words[:token_len] if len(words) > token_len else words
            
            return ' '.join(words)

        except requests.HTTPError as e:
            status_code = e.response.status_code
            
            if status_code == 403:
                # Try one more time with different user agent and referer
                try:
                    log.warning(f"403 error for {url}, retrying with different headers...")
                    time.sleep(random.uniform(1, 2))
                    
                    headers = Websearch._get_browser_headers(referer="https://www.bing.com/")
                    response = session.get(
                        url,
                        headers=headers,
                        timeout=15,
                        allow_redirects=True
                    )
                    response.raise_for_status()
                    
                    soup = BeautifulSoup(response.text, 'html.parser')
                    for element in soup(['script', 'style', 'header', 'footer', 'nav']):
                        element.decompose()
                    
                    text_content = soup.get_text(separator='\n').strip()
                    words = text_content.split()
                    words = words[:token_len] if len(words) > token_len else words
                    
                    return ' '.join(words)
                    
                except Exception:
                    print(f"403 Forbidden for {url} - Site may block scrapers. Skipping.")
                    return f"Error: HTTP 403 - Access Denied"
            
            elif status_code in [401, 402, 422]:
                print(f"HTTP Error {status_code} for {url}. Skipping.")
                return f"Error: HTTP {status_code}"
            
            else:
                print(f"HTTP Error {status_code} for {url}")
                return f"Error: HTTP {status_code}"

        except requests.Timeout:
            print(f"Timeout: Unable to fetch content from {url}")
            return "Timeout: Content could not be fetched."

        except requests.RequestException as e:
            print(f"Error fetching {url}: {e}")
            return f"Error fetching content: {str(e)}"
        
        except Exception as e:
            print(f"Unexpected error for {url}: {e}")
            return f"Error: {str(e)}"
        
        finally:
            if session:
                session.close()
