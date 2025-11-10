import asyncio
import httpx
import json

async def make_request(client, query):
    """
    Makes a POST request to the /agent endpoint.
    """
    response = await client.post(
        "http://localhost:8844/agent",
        json={
            "query": query,
            "bot_key": "test_key",
            "org": "test_org",
            "uid": "test_uid"
        },
        timeout=120  # Set a longer timeout to allow the server to process
    )
    return response

async def main():
    """
    Sends two concurrent requests to the server.
    """
    async with httpx.AsyncClient() as client:
        tasks = [
            make_request(client, "What is the capital of France?"),
            make_request(client, "What is the highest mountain in the world?")
        ]
        responses = await asyncio.gather(*tasks)

        for response in responses:
            print(f"Status Code: {response.status_code}")
            async for chunk in response.aiter_bytes():
                try:
                    # The response is a stream of JSON objects
                    data = json.loads(chunk)
                    print(data)
                except json.JSONDecodeError:
                    # Handle cases where a chunk is not a complete JSON object
                    print(f"Received a partial chunk: {chunk}")
            print("-" * 20)

if __name__ == "__main__":
    asyncio.run(main())