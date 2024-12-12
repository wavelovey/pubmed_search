import os
import json
import logging
import sys
import asyncio
from typing import Any, Sequence
from functools import lru_cache

from Bio import Entrez
from dotenv import load_dotenv
from mcp.server import Server
from mcp.types import (
    Resource,
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
    LoggingLevel
)
from pydantic import AnyUrl

# Configure logging more verbosely
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr),
        logging.FileHandler('pubmed_search.log')
    ]
)
logger = logging.getLogger("pubmed-search")

# Load environment variables
load_dotenv()
logger.info("Starting PubMed search server...")

# Configure Entrez
email = os.getenv("ENTREZ_EMAIL")
if not email:
    logger.error("No ENTREZ_EMAIL found in environment variables")
    sys.exit(1)
    
Entrez.email = email
logger.info(f"Configured Entrez with email: {email}")

# Initialize server BEFORE defining decorators
app = Server("pubmed-search")

class PubMedSearcher:
    def __init__(self):
        self.db = "pubmed"

    async def search(self, query: str, max_results: int = 15) -> dict:
        try:
            handle = Entrez.esearch(db=self.db, term=query, retmax=max_results)
            results = Entrez.read(handle)
            handle.close()

            if not results["IdList"]:
                return {
                    "status": "no_results",
                    "query": query,
                    "message": f"No results found for '{query}'"
                }

            ids = ','.join(results["IdList"])
            handle = Entrez.efetch(db=self.db, id=ids, rettype="medline", retmode="text")
            records = handle.read()
            handle.close()

            return {
                "status": "success",
                "query": query,
                "total_results": int(results['Count']),
                "showing": len(results["IdList"]),
                "records": records
            }

        except Exception as e:
            logger.error(f"PubMed search error: {e}")
            return {
                "status": "error",
                "query": query,
                "message": str(e)
            }

# Initialize searcher
pubmed = PubMedSearcher()

@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available PubMed search tools."""
    logger.info("list_tools called")
    return [
        Tool(
            name="pubmed_search",
            description="Search PubMed medical literature database",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Medical/scientific search query"
                    },
                    "max_results": {
                        "type": "number",
                        "description": "Maximum number of results (1-15)",
                        "default": 15
                    }
                },
                "required": ["query"]
            }
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: Any) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
    """Handle tool calls for PubMed searches."""
    logger.info(f"call_tool called with name: {name}, arguments: {arguments}")
    
    if name != "pubmed_search":
        logger.error(f"Unknown tool: {name}")
        raise ValueError(f"Unknown tool: {name}")

    if not isinstance(arguments, dict) or "query" not in arguments:
        logger.error("Invalid search arguments")
        raise ValueError("Invalid search arguments")

    query = arguments["query"]
    max_results = min(int(arguments.get("max_results", 15)), 15)

    try:
        logger.info(f"Performing PubMed search for query: {query}")
        results = await pubmed.search(query, max_results)
        logger.info("Search completed successfully")

        return [
            TextContent(
                type="text",
                text=json.dumps(results, indent=2)
            )
        ]
    except Exception as e:
        logger.error(f"PubMed search error: {str(e)}")
        raise RuntimeError(f"PubMed search error: {str(e)}")

async def main():
    """Main entry point for the server."""
    logger.info("Starting main server function")
    from mcp.server.stdio import stdio_server

    try:
        async with stdio_server() as (read_stream, write_stream):
            logger.info("Server streams initialized")
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options()
            )
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        sys.exit(1)

def run_main():
    """Wrapper to run the async main function"""
    logger.info("Starting server via run_main")
    asyncio.run(main())

if __name__ == "__main__":
    run_main()